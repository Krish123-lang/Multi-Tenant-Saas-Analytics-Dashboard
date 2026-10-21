from django.db import models

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner",
        ADMIN = "ADMIN", "Admin",
        ANALYST = "ANALYST", "Analyst"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ANALYST)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_user_per_organization",
            ),
        ]

    def __str__(self):
        return (f"{self.user} - {self.organization} " f"{self.role}")
