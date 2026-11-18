from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="venta",
            name="nombre_fiado",
            field=models.CharField(
                blank=True,
                max_length=150,
                default="",
                help_text="Nombre libre del cliente cuando el fiado es sin cuenta registrada.",
            ),
            preserve_default=False,
        ),
    ]
