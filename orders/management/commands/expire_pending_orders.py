from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order


class Command(BaseCommand):
    help = 'Помечает просроченные заказы со статусом pending как expired'

    def handle(self, *args, **options):
        now = timezone.now()
        updated = Order.objects.filter(
            status='pending',
            expires_at__lt=now,
        ).update(status='expired')
        self.stdout.write(self.style.SUCCESS(f'Просрочено заказов: {updated}'))
