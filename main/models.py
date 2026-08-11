from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)

    is_active = models.BooleanField(default=True, help_text="Скрыть категорию с сайта")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=20)

    class Meta:
        verbose_name = "Размер"
        verbose_name_plural = "Размеры"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='products'
    )
    color = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    main_image = models.ImageField(upload_to='products/main/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self):
        return self.name


class ProductSize(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='product_sizes'
    )
    size = models.ForeignKey(Size, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'size'], name='unique_product_size')
        ]

    def __str__(self):
        return f"{self.size.name} ({self.stock} in stock) for {self.product.name}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to='products/extra/')


class Banner(models.Model):
    title = models.CharField("Заголовок", max_length=255)
    subtitle = models.TextField("Подзаголовок", blank=True)
    image = models.ImageField("Изображение", upload_to='banners/')
    button_text = models.CharField("Текст кнопки", max_length=50, default="ПОДРОБНЕЕ")
    link = models.CharField("Ссылка (URL или slug)", max_length=255, default="/")
    order = models.PositiveIntegerField("Порядок", default=0, help_text="Меньшее число = раньше")
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Баннер"
        verbose_name_plural = "Баннеры"
        ordering = ['order']

    def __str__(self):
        return self.title
