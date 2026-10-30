from django.db import migrations, models


def renomear(apps, schema_editor):
    Usuario = apps.get_model("contas", "Usuario")
    Usuario.objects.filter(papel="recepcao").update(papel="administrador")
    Usuario.objects.filter(papel="gestao").update(papel="sesmt")


def reverter(apps, schema_editor):
    Usuario = apps.get_model("contas", "Usuario")
    Usuario.objects.filter(papel="administrador").update(papel="recepcao")
    Usuario.objects.filter(papel="sesmt").update(papel="gestao")


class Migration(migrations.Migration):

    dependencies = [
        ("contas", "0003_lembrete_checkin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usuario",
            name="papel",
            field=models.CharField(
                choices=[
                    ("colaborador", "Colaborador"),
                    ("massoterapeuta", "Massoterapeuta"),
                    ("administrador", "Administrador"),
                    ("sesmt", "SESMT"),
                ],
                default="colaborador",
                max_length=20,
            ),
        ),
        migrations.RunPython(renomear, reverter),
    ]
