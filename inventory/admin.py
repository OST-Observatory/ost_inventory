from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Category, Item, Loan, Location, Project, Stocktake, StocktakeScan


class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "path_display")
    search_fields = ("name",)
    list_filter = ("parent",)


class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name",)
    ordering = ("sort_order", "name")


class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class ItemResource(resources.ModelResource):
    class Meta:
        model = Item
        fields = (
            "id",
            "name",
            "description",
            "quantity",
            "quantity_is_approximate",
            "project__name",
            "location",
            "container",
            "installed_in",
            "comment",
            "is_active",
        )


class ItemAdmin(ImportExportModelAdmin):
    resource_classes = [ItemResource]
    list_display = (
        "id",
        "name",
        "location",
        "container",
        "installed_in",
        "project",
        "is_active",
        "is_lent_display",
    )
    list_filter = ("is_active", "categories", "project", "location")
    search_fields = ("name", "description", "comment", "container", "installed_in__name")
    raw_id_fields = ("location", "project", "installed_in", "created_by", "updated_by")
    filter_horizontal = ("categories",)

    @admin.display(boolean=True, description="On loan")
    def is_lent_display(self, obj):
        return obj.is_lent


class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "borrower_name",
        "borrowed_at",
        "due_date",
        "returned_at",
        "recorded_by",
    )
    list_filter = ("due_date",)
    search_fields = ("borrower_name", "borrower_contact", "item__name")
    raw_id_fields = ("item", "recorded_by")


admin.site.register(Location, LocationAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(Loan, LoanAdmin)
admin.site.register(Stocktake)
admin.site.register(StocktakeScan)
