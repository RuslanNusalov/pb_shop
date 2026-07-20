from django.db import models
from django.conf import settings


class Wishlist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist')
    products = models.ManyToManyField(
        'main.ProductSize',  # ← Важно: ProductSize, а не Product
        related_name='wishlisted_by',
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Избранное: {self.user.username}"

    @property
    def count(self):
        return self.products.count()

    class Meta:
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"