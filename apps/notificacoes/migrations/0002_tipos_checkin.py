from django.db import migrations, models


def para_frente(apps, schema_editor):
    apps.get_model("notificacoes", "Notificacao").objects.filter(tipo="checkin").update(tipo="chegada")


def para_tras(apps, schema_editor):
    apps.get_model("notificacoes", "Notificacao").objects.filter(tipo="chegada").update(tipo="checkin")


class Migration(migrations.Migration):
    dependencies = [
        ("notificacoes", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificacao",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("lembrete", "Lembrete de check-in"),
                    ("ultimo_aviso", "Último aviso de check-in"),
                    ("liberado", "Reserva liberada (sem check-in)"),
                    ("novo", "Novo agendamento"),
                    ("chegada", "Chegada"),
                    ("cancelamento", "Cancelamento"),
                    ("proximo", "Próximo atendimento"),
                    ("teste", "Teste"),
                ],
                max_length=15,
            ),
        ),
        migrations.RunPython(para_frente, para_tras),
    ]
