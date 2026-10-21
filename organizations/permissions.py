from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Membership


class IsOrganizationMember(BasePermission):
    """
    Members can read their organization.
    Owners and admins can modify it.
    """

    def has_object_permission(self, request, view, obj):
        membership = Membership.objects.filter(
            organization=obj, user=request.user,).first()

        if membership is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        return membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN,]
