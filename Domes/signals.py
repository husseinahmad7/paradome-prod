# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Dome, DomeMembership

# @receiver(post_save, sender=Dome)
# def create_project_owner_membership(sender, instance, created, **kwargs):
#     if created:
#         DomeMembership.objects.create(member=instance.user, dome=instance, access_level=2)