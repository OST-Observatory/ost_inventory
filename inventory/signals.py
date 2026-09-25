"""Remove photo files (and their thumbnails) that no item refers to any more.

Covers deleting an item, replacing a photo (detail page) and clearing/replacing it in the
edit form. Files are deleted only after the transaction commits, so a rollback keeps them.
"""
from functools import partial

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from inventory.images import delete_photo_file
from inventory.models import Item


@receiver(pre_save, sender=Item)
def remember_old_photo(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_photo_name = ""
        return
    old = sender.objects.filter(pk=instance.pk).values_list("photo", flat=True).first()
    instance._old_photo_name = old or ""


@receiver(post_save, sender=Item)
def delete_replaced_photo(sender, instance, **kwargs):
    old_name = getattr(instance, "_old_photo_name", "")
    if old_name and old_name != (instance.photo.name or ""):
        transaction.on_commit(partial(delete_photo_file, old_name, instance.photo.storage))


@receiver(post_delete, sender=Item)
def delete_photo_of_deleted_item(sender, instance, **kwargs):
    if instance.photo:
        transaction.on_commit(partial(delete_photo_file, instance.photo.name, instance.photo.storage))
