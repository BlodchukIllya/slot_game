# Generated by Django 5.2 on 2025-05-01 07:28

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='GameResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('numbers', models.CharField(max_length=20)),
                ('is_win', models.BooleanField()),
            ],
        ),
    ]
