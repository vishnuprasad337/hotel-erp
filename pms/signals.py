from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking

@receiver(post_save, sender=Booking)
def push_booking_to_website_channel(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from channelmanager.views import push_booking_to_website
        channel = instance.room.hotel.website_channel
        if channel and channel.is_active and channel.callback_url and channel.outbound_api_key:
            push_booking_to_website(channel, instance)
    except Exception:
        return