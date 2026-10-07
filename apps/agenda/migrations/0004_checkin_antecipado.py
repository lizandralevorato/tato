"""Check-in passa a ser a confirmação antecipada (prazo 1 h antes, tolerância 5 min).

O antigo "check-in" (aviso de chegada na sala) vira "chegada".
"""

from django.db import migrations, models
from django.db.models import Q


def renomear_status(apps, schema_editor, de, para):
    Agendamento = apps.get_model("agenda", "Agendamento")
    Agendamento.objects.filter(status=de).update(status=para)


def para_frente(apps, schema_editor):
    renomear_status(apps, schema_editor, "checkin", "chegou")


def para_tras(apps, schema_editor):
    renomear_status(apps, schema_editor, "chegou", "checkin")
    Agendamento = apps.get_model("agenda", "Agendamento")
    Agendamento.objects.filter(status="expirado").update(status="cancelado")


class Migration(migrations.Migration):
    dependencies = [
        ("agenda", "0003_politicabeneficio_aviso_proximo_min_and_more"),
    ]

    operations = [
        # Política
        migrations.RenameField("politicabeneficio", "checkin_abre_min", "chegada_abre_min"),
        migrations.AlterField(
            model_name="politicabeneficio",
            name="chegada_abre_min",
            field=models.PositiveSmallIntegerField(
                default=10, verbose_name="botão 'Cheguei' liberado quantos minutos antes"
            ),
        ),
        migrations.AddField(
            model_name="politicabeneficio",
            name="checkin_abre_min",
            field=models.PositiveSmallIntegerField(
                default=120, verbose_name="check-in abre quantos minutos antes (o lembrete sai nesse momento)"
            ),
        ),
        migrations.AddField(
            model_name="politicabeneficio",
            name="checkin_prazo_min",
            field=models.PositiveSmallIntegerField(
                default=60,
                verbose_name="prazo do check-in: até quantos minutos antes (0 = check-in não obrigatório)",
            ),
        ),
        migrations.AddField(
            model_name="politicabeneficio",
            name="checkin_tolerancia_min",
            field=models.PositiveSmallIntegerField(
                default=5, verbose_name="tolerância depois do prazo do check-in (min)"
            ),
        ),
        migrations.RemoveField(model_name="politicabeneficio", name="lembrete_min_antes"),
        # Agendamento
        migrations.RenameField("agendamento", "checkin_em", "chegada_em"),
        migrations.AlterField(
            model_name="agendamento",
            name="confirmado_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="check-in feito em"),
        ),
        migrations.AlterField(
            model_name="agendamento",
            name="status",
            field=models.CharField(
                choices=[
                    ("agendado", "Agendado"),
                    ("confirmado", "Check-in feito"),
                    ("chegou", "Chegou"),
                    ("realizado", "Atendido"),
                    ("falta", "Faltou"),
                    ("cancelado", "Cancelado"),
                    ("expirado", "Liberado (sem check-in)"),
                ],
                default="agendado",
                max_length=12,
            ),
        ),
        migrations.RunPython(para_frente, para_tras),
        migrations.RemoveConstraint(model_name="agendamento", name="um_agendamento_ativo_por_horario"),
        migrations.AddConstraint(
            model_name="agendamento",
            constraint=models.UniqueConstraint(
                condition=~Q(status__in=["cancelado", "expirado"]),
                fields=("massoterapeuta", "inicio"),
                name="um_agendamento_ativo_por_horario",
            ),
        ),
    ]
