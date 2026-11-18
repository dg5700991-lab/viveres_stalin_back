from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="email",
            field=models.EmailField(blank=True, max_length=254, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="cliente",
            name="apellidos",
            field=models.CharField(blank=True, max_length=120, default=""),
            preserve_default=False,
        ),
    ]
