from django.contrib.auth.views import LoginView, LogoutView

from accounts.throttling import clear_failures, is_locked, record_failure

from .models import sync_role_groups

_LOCKOUT_MESSAGE = "Too many login attempts. Try again later."


class InventoryLoginView(LoginView):
    template_name = "registration/login.html"

    def _username(self):
        return self.request.POST.get("username", "")

    def _lockout_response(self):
        form = self.get_form()
        form.add_error(None, _LOCKOUT_MESSAGE)
        return self.render_to_response(self.get_context_data(form=form), status=429)

    def post(self, request, *args, **kwargs):
        if is_locked(request, self._username()):
            return self._lockout_response()
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        clear_failures(self.request, form.get_user().get_username())
        response = super().form_valid(form)
        sync_role_groups(self.request.user)
        return response

    def form_invalid(self, form):
        locked = record_failure(self.request, self._username())
        if locked or is_locked(self.request, self._username()):
            return self._lockout_response()
        return super().form_invalid(form)


class InventoryLogoutView(LogoutView):
    next_page = "login"
