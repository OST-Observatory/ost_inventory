from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_default_acl(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    GroupCapability = apps.get_model("accounts", "GroupCapability")
    defaults = {
        "student": ["read"],
        "supervisor": ["read", "write", "loan_pii", "inactive", "import", "labels"],
        "staff": [
            "read",
            "write",
            "loan_pii",
            "inactive",
            "import",
            "labels",
            "delete",
            "manage_acl",
        ],
    }
    for name, caps in defaults.items():
        group, _ = Group.objects.get_or_create(name=name)
        for cap in caps:
            GroupCapability.objects.get_or_create(group=group, capability=cap)


def unseed_default_acl(apps, schema_editor):
    GroupCapability = apps.get_model("accounts", "GroupCapability")
    GroupCapability.objects.filter(
        group__name__in=["student", "supervisor", "staff"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="GroupCapability",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("capability", models.CharField(max_length=32)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_capabilities",
                        to="auth.group",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="groupcapability",
            index=models.Index(fields=["capability"], name="accounts_gr_capabil_idx"),
        ),
        migrations.AddConstraint(
            model_name="groupcapability",
            constraint=models.UniqueConstraint(
                fields=("group", "capability"),
                name="accounts_groupcapability_unique",
            ),
        ),
        migrations.RunPython(seed_default_acl, unseed_default_acl),
    ]
