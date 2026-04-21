from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance: User, created, **kwargs):
    """为每个 User 保证存在 UserProfile；已激活或超级用户默认为已通过。"""
    if kwargs.get('raw'):
        return
    status = UserProfile.Status.APPROVED
    if not instance.is_active and not instance.is_superuser:
        status = UserProfile.Status.PENDING
    profile, was_created = UserProfile.objects.get_or_create(
        user=instance,
        defaults={'registration_status': status},
    )
    if was_created:
        return
    # 已存在资料时：超级用户确保为已通过
    if instance.is_superuser and profile.registration_status != UserProfile.Status.APPROVED:
        profile.registration_status = UserProfile.Status.APPROVED
        profile.save(update_fields=['registration_status'])
