from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from accounts.acl import MANAGE_ACL, WRITE
from accounts.models import GroupCapability
from accounts.permissions import user_can_admin, user_can_write

from django.contrib.auth import get_user_model

User = get_user_model()


class AccessControlTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="x", is_staff=True
        )
        self.student = User.objects.create_user(
            username="student", password="x", is_student=True
        )
        self.client = Client()

    def test_admin_menu_and_acl_page(self):
        self.client.login(username="staff", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertContains(resp, "Access control")
        self.assertContains(resp, "Admin")
        resp = self.client.get(reverse("accounts:access"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "student")
        self.assertContains(resp, "supervisor")
        self.assertContains(resp, "staff")
        self.assertContains(resp, "Add and edit items")

    def test_student_cannot_open_acl(self):
        self.client.login(username="student", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertNotContains(resp, "Access control")
        resp = self.client.get(reverse("accounts:access"))
        self.assertEqual(resp.status_code, 403)

    def test_grant_write_to_student_group(self):
        self.assertFalse(user_can_write(self.student))
        students = Group.objects.get(name="student")
        GroupCapability.objects.get_or_create(group=students, capability=WRITE)
        self.student.__dict__.pop("_inventory_capabilities", None)
        self.assertTrue(user_can_write(self.student))

        self.client.login(username="student", password="x")
        resp = self.client.get(reverse("inventory:item_create"))
        self.assertEqual(resp.status_code, 200)

    def test_cannot_remove_own_manage_acl(self):
        staff_group = Group.objects.get(name="staff")
        self.client.login(username="staff", password="x")
        post = {}
        for group in Group.objects.all():
            caps = set(
                GroupCapability.objects.filter(group=group).values_list(
                    "capability", flat=True
                )
            )
            if group.pk == staff_group.pk:
                caps.discard(MANAGE_ACL)
            for cap in caps:
                post[f"cap_{group.pk}_{cap}"] = "on"
        resp = self.client.post(reverse("accounts:access_save"), post)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            GroupCapability.objects.filter(
                group=staff_group, capability=MANAGE_ACL
            ).exists()
        )
        self.assertTrue(user_can_admin(User.objects.get(pk=self.staff.pk)))

    def test_create_group_and_assign_member(self):
        self.client.login(username="staff", password="x")
        resp = self.client.get(reverse("accounts:groups"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(
            reverse("accounts:group_add"), {"name": "helpers"}
        )
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name="helpers")
        resp = self.client.post(
            reverse("accounts:group_add_member", args=[group.pk]),
            {"username": "student"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(group.user_set.filter(pk=self.student.pk).exists())
        resp = self.client.post(
            reverse("accounts:group_delete", args=[Group.objects.get(name="student").pk])
        )
        self.assertTrue(Group.objects.filter(name="student").exists())
        resp = self.client.post(reverse("accounts:group_delete", args=[group.pk]))
        self.assertFalse(Group.objects.filter(name="helpers").exists())
