from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Membership, Organization

User = get_user_model()

class OrganizationAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner",password="test-password-123",)
        self.analyst = User.objects.create_user(username="analyst",password="test-password-123",)
        self.outsider = User.objects.create_user(username="outsider",password="test-password-123",)
        self.organization = Organization.objects.create(name="ABC Retail",)
        Membership.objects.create(organization=self.organization,user=self.owner,role=Membership.Role.OWNER,)
        Membership.objects.create(organization=self.organization,user=self.analyst,role=Membership.Role.ANALYST,)
        self.list_url = reverse("organization-list")
        self.detail_url = reverse("organization-detail",args=[self.organization.id],)

    def test_unauthenticated_user_is_denied(self):
        response = self.client.get(self.list_url)
        self.assertIn(response.status_code,[status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,],)

    def test_list_only_returns_member_organizations(self):
        self.client.force_authenticate(user=self.analyst)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"],self.organization.id,)

    def test_non_member_cannot_retrieve_organization(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code,status.HTTP_404_NOT_FOUND,)

    def test_analyst_cannot_update_organization(self):
        self.client.force_authenticate(user=self.analyst)
        response = self.client.patch(self.detail_url,{"name": "Unauthorized Rename"},format="json",)
        self.assertEqual(response.status_code,status.HTTP_403_FORBIDDEN,)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name,"ABC Retail",)

    def test_owner_can_update_organization(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(self.detail_url,{"name": "ABC Retail Updated"},format="json",)
        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name,"ABC Retail Updated",)

    def test_creating_organization_assigns_owner(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(self.list_url,{"name": "Northstar Analytics"},format="json",)
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,)
        organization = Organization.objects.get(name="Northstar Analytics",)
        self.assertTrue(Membership.objects.filter(organization=organization,user=self.owner,role=Membership.Role.OWNER,).exists())