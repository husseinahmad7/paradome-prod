# Generated by Django 4.1 on 2022-09-23 04:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Chat', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chatmessage',
            name='file',
        ),
    ]