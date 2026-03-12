from django.db import models
from django.contrib.auth.models import User
import uuid


class Environment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    base_url = models.TextField()
    auth_type = models.TextField(
        default='password_only',
        choices=[
            ('password_only', 'Password Only'),
            ('username_password', 'Username + Password'),
            ('none', 'None'),
        ]
    )
    credentials = models.JSONField(default=dict)
    launcher_config = models.JSONField(default=dict)
    notes = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'environments'
        ordering = ['name']

    def __str__(self):
        return self.name


class UserEnvironment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='environment_access')
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name='user_access')

    class Meta:
        db_table = 'user_environments'
        unique_together = ('user', 'environment')

    def __str__(self):
        return f"{self.user.username} → {self.environment.name}"


class Assessment(models.Model):
    id = models.TextField(primary_key=True)
    numeric_id = models.IntegerField(unique=True, editable=False)
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name='assessments',
        null=True, blank=True
    )
    name = models.TextField()
    subject = models.TextField(null=True, blank=True)
    grade = models.TextField(null=True, blank=True)
    year = models.TextField(null=True, blank=True)
    item_count = models.IntegerField(null=True, blank=True)
    form_value = models.TextField(null=True, blank=True)
    intro_screens = models.IntegerField(default=5)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assessments'
        ordering = ['name']

    def __str__(self):
        return self.name


class Item(models.Model):
    # numeric_id is the auto PK (used in URLs)
    numeric_id = models.AutoField(primary_key=True)
    # item_id is the NAEP text identifier
    item_id = models.TextField(unique=True)
    # Keep 'id' as an alias for item_id for legacy compatibility
    title = models.TextField(null=True, blank=True)
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name='items',
        db_column='environment_id'
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='items', db_column='assessment_id'
    )
    position = models.IntegerField(null=True, blank=True)
    category = models.TextField(null=True, blank=True)
    tier = models.TextField(null=True, blank=True)
    languages = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'items'
        ordering = ['numeric_id']

    def __str__(self):
        return f"{self.item_id} — {self.title or 'Untitled'}"


class Baseline(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='baselines',
                             db_column='item_id', to_field='item_id')
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name='baselines',
        null=True, blank=True
    )
    browser = models.TextField()
    device_profile = models.TextField()
    version = models.TextField()
    screenshot_path = models.TextField()
    approved_by = models.TextField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'baselines'
        unique_together = ('item', 'browser', 'device_profile', 'version')


class TestSuite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    created_by = models.TextField(null=True, blank=True)
    schedule = models.JSONField(null=True, blank=True)
    browser_profiles = models.JSONField(default=list)
    environment = models.ForeignKey(
        Environment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='suites'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'test_suites'
        ordering = ['name']

    def __str__(self):
        return self.name


class TestSuiteScript(models.Model):
    suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, related_name='scripts')
    script_path = models.TextField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'test_suite_scripts'
        unique_together = ('suite', 'script_path')


class TestRun(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    suite = models.ForeignKey(
        TestSuite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='runs'
    )
    environment = models.ForeignKey(
        Environment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='runs'
    )
    status = models.TextField(default='running', choices=STATUS_CHOICES)
    trigger_type = models.TextField(default='manual')
    config = models.JSONField(default=dict)
    summary = models.JSONField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'test_runs'
        ordering = ['-queued_at']

    def __str__(self):
        return f"Run {str(self.id)[:8]} ({self.status})"


class TestRunScript(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('error', 'Error'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='script_results')
    script_path = models.TextField()
    status = models.TextField(default='queued', choices=STATUS_CHOICES)
    duration_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    execution_log = models.TextField(null=True, blank=True)
    trace_path = models.TextField(null=True, blank=True)
    video_path = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'test_run_scripts'
        ordering = ['script_path']


class TestResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='results')
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='item_id', to_field='item_id'
    )
    browser = models.TextField()
    device_profile = models.TextField(null=True, blank=True)
    status = models.TextField()
    duration_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    screenshot_path = models.TextField(null=True, blank=True)
    diff_path = models.TextField(null=True, blank=True)
    diff_ratio = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'test_results'


class AIAnalysis(models.Model):
    ANALYSIS_TYPE_CHOICES = [
        ('text_content', 'Text Content'),
        ('visual_layout', 'Visual Layout'),
        ('screenshot_diff', 'Screenshot Diff'),
        ('screenshot', 'Screenshot'),  # Legacy
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='ai_analyses')
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='item_id', to_field='item_id'
    )
    test_result = models.ForeignKey(
        TestResult, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_analyses'
    )
    analysis_type = models.TextField(choices=ANALYSIS_TYPE_CHOICES)
    status = models.TextField(default='pending')
    issues_found = models.BooleanField(default=False)
    issues = models.JSONField(default=list)
    raw_response = models.TextField(null=True, blank=True)
    model_used = models.TextField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_analyses'


class Review(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('dismissed', 'Dismissed'),
        ('bug_filed', 'Bug Filed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(AIAnalysis, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.TextField(default='pending', choices=STATUS_CHOICES)
    notes = models.TextField(null=True, blank=True)
    bug_url = models.TextField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviews'
        ordering = ['-created_at']


class TestScript(models.Model):
    TEST_TYPE_CHOICES = [
        ('functional', 'Functional'),
        ('visual_regression', 'Visual Regression'),
        ('ai_content', 'AI Content Analysis'),
        ('ai_visual', 'AI Visual Analysis'),
    ]

    id = models.AutoField(primary_key=True)
    script_path = models.TextField(unique=True)
    description = models.TextField(null=True, blank=True)
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name='test_scripts',
        db_column='environment_id'
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='item_id', to_field='item_id'
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='assessment_id'
    )
    test_type = models.TextField(default='functional', choices=TEST_TYPE_CHOICES)
    ai_config = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list)
    category = models.TextField(null=True, blank=True)
    chat_conversation = models.ForeignKey(
        'AIConversation', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='chat_conversation_id', related_name='test_scripts'
    )
    test_summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'test_scripts'

    def __str__(self):
        return self.script_path


class AISetting(models.Model):
    key = models.TextField(primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_settings'

    def __str__(self):
        return self.key


class AITool(models.Model):
    id = models.TextField(primary_key=True)
    name = models.TextField()
    description = models.TextField()
    category = models.TextField(default='general')
    enabled = models.BooleanField(default=True)
    parameters = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_tools'

    def __str__(self):
        return self.name


class TestDataSet(models.Model):
    DATA_TYPE_CHOICES = [
        ('credentials', 'Credentials'),
        ('inputs', 'Test Inputs'),
        ('items', 'Item List'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name='test_data_sets'
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='test_data_sets'
    )
    data_type = models.TextField(choices=DATA_TYPE_CHOICES)
    data = models.JSONField(default=list)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'test_data_sets'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.data_type})"


class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')
    timezone = models.CharField(max_length=63, default='America/New_York')

    class Meta:
        db_table = 'user_settings'

    def __str__(self):
        return f"{self.user.username} — {self.timezone}"


class RunScreenshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='screenshots')
    run_script = models.ForeignKey(
        TestRunScript, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='screenshots'
    )
    name = models.TextField()
    file_path = models.TextField()
    project_name = models.TextField(default='chrome-desktop')
    flagged = models.BooleanField(default=False)
    flag_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'run_screenshots'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({'flagged' if self.flagged else 'ok'})"


class AIConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    messages = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_conversations'
        ordering = ['-last_active_at']
