from rest_framework.permissions import BasePermission, SAFE_METHODS

from organizations.models import Membership

class IsDatasetMember(BasePermission):
    def has_object_permission(self, request, view, obj):
        membership = Membership.objects.filter(organization=obj.organization, user=request.user,).first()

        if membership is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        return membership.role in [
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        ]
