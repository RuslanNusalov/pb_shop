from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order

class Command(BaseCommand):
    help = 'Автоматически отменяет просроченные заказы'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # ✅ ИСПРАВЛЕНО: используем expires_at
        expired_orders = Order.objects.filter(
            status='pending',       # Убедись, что 'pending' — это верный статус "ожидает оплаты"
            expires_at__lt=now      # ✅ Используем expires_at
        )
        
        count = expired_orders.count()
        
        if count > 0:
            expired_orders.update(status='cancelled')
            self.stdout.write(self.style.SUCCESS(f'✅ Статус обновлён для {count} заказов.'))
        else:
            self.stdout.write(self.style.WARNING('⏳ Просроченных заказов не найдено.'))