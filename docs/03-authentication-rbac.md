# Authentication & Role-Based Access Control

## Authentication

SCOUT uses Django's built-in session authentication. There is no token-based or OAuth flow.

### Login / Logout

| Route | View | Behavior |
|-------|------|----------|
| `GET /login/` | `core.views.login_view` | Renders the login form (`templates/login.html`) |
| `POST /login/` | `core.views.login_view` | Authenticates via `django.contrib.auth.authenticate()`; on success, calls `login()` and redirects to `?next=` or `/` |
| `GET /logout/` | `core.views.logout_view` | Calls `logout()`, redirects to `/login/` |

### Settings

```python
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
```

---

## Roles

SCOUT has three effective roles, derived from Django's built-in user flags:

| Role | Flag | Access |
|------|------|--------|
| **Superuser** | `is_superuser=True` | Full app + Django Admin (`/django-admin/`) |
| **Admin** | `is_staff=True` | Full app access; can manage environments, AI config, users |
| **User** | (neither flag) | Restricted to environments explicitly assigned via `UserEnvironment` |

### Assigning Environments to Users

A superuser or admin creates a `UserEnvironment` row linking a user to an environment. This can be done via the Django Admin at `/django-admin/core/userenvironment/add/`.

Once assigned, the user sees only assessments, items, suites, and runs that belong to those environments.

---

## Access Control Implementation

### `EnvironmentScopedMixin` (`core/mixins.py`)

All list views that filter by environment use this mixin (or its standalone helper).

```python
class EnvironmentScopedMixin(LoginRequiredMixin):
    def get_user_environment_ids(self):
        if self.request.user.is_staff:
            return None        # None = no filter applied = all environments
        return list(
            UserEnvironment.objects.filter(user=self.request.user)
            .values_list('environment_id', flat=True)
        )
```

#### Standalone function

For function-based views (which is the majority of SCOUT views), a module-level helper is used:

```python
def get_user_env_ids(user):
    if user.is_staff:
        return None
    return list(
        UserEnvironment.objects.filter(user=user)
        .values_list('environment_id', flat=True)
    )
```

#### How it is applied in SQL

Views that scope by environment inject `env_ids` into raw SQL:

```python
env_ids = get_user_env_ids(request.user)

if env_ids is None:
    # Admin: no filter
    cursor.execute("SELECT ... FROM test_suites ...")
else:
    # User: filter to assigned environments
    cursor.execute(
        "SELECT ... FROM test_suites WHERE environment_id = ANY(%s::uuid[])",
        [[str(e) for e in env_ids]]
    )
```

If a non-admin user has no environment assignments, `env_ids` is an empty list and the query returns no rows.

---

### `LoginRequiredMixin` (`core/mixins.py`)

Subclass of `django.contrib.auth.mixins.LoginRequiredMixin` with `login_url` set to `/login/`. Applied to all class-based views.

For function-based views, the `@login_required(login_url='/login/')` decorator is used directly.

---

### `AdminRequiredMixin` (`core/mixins.py`)

Used for views that require `is_staff`:

```python
class AdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseForbidden('Admin access required.')
        return super().dispatch(request, *args, **kwargs)
```

---

### `admin_required` decorator (`environments/views.py`, `admin_config/views.py`)

Some modules use a custom function decorator instead of the mixin:

```python
def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not request.user.is_staff:
            return HttpResponseForbidden('Admin access required.')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper
```

This is functionally equivalent to `AdminRequiredMixin` for function-based views.

---

## Which Views Require Which Role

| Section | Min Role | Notes |
|---------|----------|-------|
| Dashboard | User | Scoped to user's environments |
| Runs | User | Scoped |
| Suites | User | Scoped |
| Items | User | Scoped via assessment → environment |
| Assessments | User | Scoped |
| Reviews | User | Scoped (implicitly, via item → assessment) |
| Test Cases | User | Unscoped (scripts are global) |
| Builder | User | Unscoped |
| Environments | **Admin** | Full CRUD — admin only |
| Admin Config | **Admin** | AI settings — admin only |
| Django Admin | **Superuser** | `/django-admin/` |

---

## Context Processor

`core/context_processors.nav_context` injects two variables into every template:

| Variable | Type | Contents |
|----------|------|----------|
| `nav_environments` | `QuerySet` | Environments visible to the current user (filtered by `UserEnvironment` for non-admins; all for admins) |
| `is_admin` | `bool` | `request.user.is_staff` |

These drive the sidebar: the environment dropdown in the nav lists only accessible environments, and admin-only links are conditionally shown with `{% if is_admin %}`.
