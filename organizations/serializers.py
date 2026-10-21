from django.db import transaction
from rest_framework import serializers

from .models import Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "created_at", "updated_at",]
        read_only_fields = ["id", "slug", "created_at", "updated_at",]

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        organization = Organization.objects.create(**validated_data)
        Membership.objects.create(organization=organization, user=user, role=Membership.Role.OWNER,)
        return organization
