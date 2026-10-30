from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar(self, email, password, **extra):
        if not email:
            raise ValueError("Informe o e-mail.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._criar(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("papel", Usuario.Papel.ADMINISTRADOR)
        return self._criar(email, password, **extra)


class Usuario(AbstractUser):
    """Usuário que entra com e-mail. O papel define quais telas ele vê."""

    class Papel(models.TextChoices):
        COLABORADOR = "colaborador", "Colaborador"
        MASSOTERAPEUTA = "massoterapeuta", "Massoterapeuta"
        ADMINISTRADOR = "administrador", "Administrador"
        SESMT = "sesmt", "SESMT"

    username = None
    email = models.EmailField("e-mail", unique=True)
    papel = models.CharField(
        max_length=20, choices=Papel.choices, default=Papel.COLABORADOR
    )
    unidade = models.ForeignKey(
        "agenda.Unidade",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usuarios",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if self.pk and self.papel != self.Papel.MASSOTERAPEUTA and hasattr(self, "massoterapeuta"):
            raise ValidationError(
                {"papel": "Esta pessoa tem cadastro de massoterapeuta. Remova o cadastro antes de mudar o papel."}
            )

    @property
    def nome(self):
        return self.get_full_name() or self.email

    @property
    def eh_massoterapeuta(self):
        return self.papel == self.Papel.MASSOTERAPEUTA

    @property
    def eh_equipe(self):
        """Administrador e SESMT tratam exceções de qualquer agendamento."""
        return self.papel in {self.Papel.ADMINISTRADOR, self.Papel.SESMT} or self.is_superuser


class PerfilAcessibilidade(models.Model):
    """Preferências de interface de cada pessoa.

    Ficam no banco (e não no navegador) para acompanhar a pessoa em qualquer
    aparelho. Guardamos só a preferência de interface, nunca diagnóstico (LGPD).
    """

    class Tema(models.TextChoices):
        SISTEMA = "sistema", "Igual ao do meu celular ou computador"
        CLARO = "claro", "Claro"
        ESCURO = "escuro", "Escuro"
        AC_ESCURO = "ac-escuro", "Alto contraste escuro (amarelo e branco sobre preto)"
        AC_CLARO = "ac-claro", "Alto contraste claro (preto sobre branco)"

    class Fonte(models.TextChoices):
        PADRAO = "padrao", "Padrão"
        LEGIVEL = "legivel", "Alta legibilidade (letras mais fáceis de distinguir)"

    TAMANHOS = [
        (100, "Normal"),
        (125, "Grande"),
        (150, "Maior"),
        (200, "Muito grande"),
        (250, "Máximo"),
    ]
    LEMBRETES_CHECKIN = [
        (15, "15 minutos antes"),
        (30, "30 minutos antes"),
        (45, "45 minutos antes"),
        (60, "1 hora antes"),
        (120, "2 horas antes"),
        (180, "3 horas antes"),
    ]
    VELOCIDADES = [
        (75, "Devagar"),
        (100, "Normal"),
        (125, "Rápida"),
        (150, "Muito rápida"),
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_acessibilidade",
    )
    tamanho_texto = models.PositiveSmallIntegerField(
        "tamanho do texto", choices=TAMANHOS, default=100
    )
    tema = models.CharField("cores", max_length=12, choices=Tema.choices, default=Tema.SISTEMA)
    fonte = models.CharField("tipo de letra", max_length=10, choices=Fonte.choices, default=Fonte.PADRAO)
    espacamento_ampliado = models.BooleanField("aumentar espaço entre linhas e letras", default=False)
    reduzir_movimento = models.BooleanField("desligar animações", default=False)
    modo_simplificado = models.BooleanField(
        "modo simplificado (menos informação por tela)", default=False
    )
    fala_ativa = models.BooleanField("avisos falados pelo site", default=False)
    fala_velocidade = models.PositiveSmallIntegerField(
        "velocidade da fala", choices=VELOCIDADES, default=100
    )
    lembrete_checkin_min = models.PositiveSmallIntegerField(
        "lembrar do check-in quanto tempo antes do prazo", choices=LEMBRETES_CHECKIN, default=60
    )
    vibracao = models.BooleanField("vibrar o celular nos avisos", default=True)
    som = models.BooleanField("tocar um som curto nos avisos", default=True)
    libras = models.BooleanField("abrir o tradutor de Libras (VLibras) em todas as telas", default=False)
    configurado = models.BooleanField(default=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil de acessibilidade"
        verbose_name_plural = "perfis de acessibilidade"

    def __str__(self):
        return f"Preferências de {self.usuario}"

    @property
    def classes_html(self):
        classes = [f"tema-{self.tema}", f"texto-{self.tamanho_texto}", f"fonte-{self.fonte}"]
        if self.espacamento_ampliado:
            classes.append("espacamento-ampliado")
        if self.reduzir_movimento:
            classes.append("reduzir-movimento")
        if self.modo_simplificado:
            classes.append("modo-simplificado")
        return " ".join(classes)
