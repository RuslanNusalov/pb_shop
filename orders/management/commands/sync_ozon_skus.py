import csv
import logging
import re

from django.core.management.base import BaseCommand
from django.db.models import Q

from main.models import Product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Синхронизирует SKU Ozon для товаров из CSV/Excel файла'

    def add_arguments(self, parser):
        parser.add_argument(
            'file',
            type=str,
            help='Путь к файлу с данными Ozon (CSV или Excel)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет обновлено, без реальных изменений'
        )
        parser.add_argument(
            '--match-by',
            type=str,
            default='name',
            choices=['name', 'article', 'sku'],
            help='Поле для сопоставления товаров (name, article, sku)'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']
        match_by = options['match_by']

        self.stdout.write(f"📂 Читаем файл: {file_path}")
        self.stdout.write(f"🔍 Сопоставление по: {match_by}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN — изменения не будут сохранены"))

        # 1. Читаем файл
        try:
            if file_path.endswith('.csv'):
                data = self._read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                data = self._read_excel(file_path)
            else:
                self.stdout.write(self.style.ERROR("❌ Поддерживаются только CSV и Excel файлы"))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Ошибка чтения файла: {e}"))
            return

        self.stdout.write(f"✅ Прочитано {len(data)} строк из файла")
        if data:
            self.stdout.write(self.style.WARNING(f"🔍 Колонки в файле: {list(data[0].keys())}"))

        # 2. Обрабатываем каждую строку
        updated_count = 0
        not_found_count = 0
        already_set_count = 0

        for row in data:
            ozon_sku = row.get('SKU')
            article = row.get('Артикул')
            name = row.get('Название товара')

            if not ozon_sku:
                continue

            # Очищаем SKU (оставляем только цифры)
            ozon_sku_clean = ''.join(c for c in str(ozon_sku) if c.isdigit())
            if not ozon_sku_clean:
                continue

            # 3. Ищем товар в БД
            product = self._find_product(name, article, match_by)

            if not product:
                not_found_count += 1
                if not_found_count <= 5:  # Показываем первые 5 не найденных
                    self.stdout.write(self.style.WARNING(f"⚠️  Не найден товар: name={name}, article={article}"))
                continue

            # 4. Проверяем, не установлен ли уже SKU
            if product.ozon_sku and product.ozon_sku == ozon_sku_clean:
                already_set_count += 1
                continue

            # 5. Обновляем SKU
            old_sku = product.ozon_sku
            product.ozon_sku = ozon_sku_clean

            if not dry_run:
                product.save()

            updated_count += 1
            self.stdout.write(
                f"✅ {product.name[:50]}: {old_sku or 'нет'} → {ozon_sku_clean}"
            )

        # 6. Итоговая статистика
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"📊 Итоги:"))
        self.stdout.write(f"   Обновлено: {updated_count}")
        self.stdout.write(f"   Уже было установлено: {already_set_count}")
        self.stdout.write(f"   Не найдено в БД: {not_found_count}")
        self.stdout.write("="*60)

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  Это был DRY RUN. Запустите без --dry-run для реального обновления."))

    def _read_csv(self, file_path):
        """Читает CSV файл с автоопределением кодировки"""
        # Пробуем разные кодировки
        for encoding in ['utf-8', 'windows-1251', 'cp1251', 'latin1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    # Определяем разделитель
                    sample = f.read(2048)
                    f.seek(0)
                    
                    # Пробуем разные разделители
                    for delimiter in [',', ';', '\t']:
                        try:
                            reader = csv.DictReader(f, delimiter=delimiter)
                            rows = list(reader)
                            if rows:
                                return rows
                        except Exception:
                            continue
            except UnicodeDecodeError:
                continue
        
        raise Exception("Не удалось прочитать CSV файл. Проверьте кодировку и формат.")

    def _read_excel(self, file_path):
        """Читает Excel файл"""
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            return df.to_dict('records')
        except ImportError:
            raise Exception("Для чтения Excel файлов установите pandas: pip install pandas openpyxl")
        except Exception as e:
            raise Exception(f"Ошибка чтения Excel: {e}")

    def _find_product(self, name, article, match_by):
        """Ищет товар в БД по разным критериям"""
        if not name and not article:
            return None

        # Стратегия 1: По артикулу (точное совпадение)
        if article and match_by in ['article', 'sku']:
            try:
                product = Product.objects.get(
                    Q(article=article) | Q(vendor_code=article) | Q(sku=article)
                )
                return product
            except Product.DoesNotExist:
                pass
            except Product.MultipleObjectsReturned:
                return Product.objects.filter(
                    Q(article=article) | Q(vendor_code=article) | Q(sku=article)
                ).first()

        # Стратегия 2: По названию (нечёткое совпадение)
        if name and match_by in ['name', 'article']:
            # Очищаем название от лишних символов
            name_clean = self._clean_name(name)
            
            # Ищем по точному совпадению очищенного названия
            try:
                product = Product.objects.get(name__iexact=name_clean)
                return product
            except Product.DoesNotExist:
                pass

            # Ищем по частичному совпадению (название содержит ключевые слова)
            keywords = self._extract_keywords(name_clean)
            if keywords:
                query = Q()
                for keyword in keywords[:3]:  # Берём первые 3 ключевых слова
                    query |= Q(name__icontains=keyword)
                
                products = Product.objects.filter(query)
                if products.count() == 1:
                    return products.first()
                elif products.count() > 1:
                    # Если найдено несколько, берём с наиболее похожим названием
                    return products.first()

        return None

    def _clean_name(self, name):
        """Очищает название от лишних символов"""
        if not name:
            return ''
        # Убираем лишние пробелы, спецсимволы
        name = re.sub(r'\s+', ' ', str(name)).strip()
        name = re.sub(r'[^\w\sа-яА-ЯёЁ-]', '', name)
        return name.lower()

    def _extract_keywords(self, name):
        """Извлекает ключевые слова из названия"""
        # Убираем стоп-слова
        stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'от', 'до', 'the', 'and', 'or'}
        words = name.split()
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 2]
        return keywords