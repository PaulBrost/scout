from django.contrib import admin
from .models import (
    Environment, UserEnvironment, Assessment, Item, Baseline,
    TestSuite, TestSuiteScript, TestRun, TestRunScript, TestResult,
    AIAnalysis, Review, TestScript, AISetting, AITool, AIConversation,
    TestDataSet,
)

@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_url', 'auth_type', 'is_default', 'created_at']
    search_fields = ['name', 'base_url']

@admin.register(UserEnvironment)
class UserEnvironmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'environment']
    list_filter = ['environment']

@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'environment', 'subject', 'grade', 'year']
    list_filter = ['environment', 'subject']
    search_fields = ['id', 'name']

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['numeric_id', 'item_id', 'title', 'environment', 'assessment', 'category', 'tier']
    search_fields = ['item_id', 'title']
    list_filter = ['environment', 'category', 'tier', 'assessment']

@admin.register(TestSuite)
class TestSuiteAdmin(admin.ModelAdmin):
    list_display = ['name', 'environment', 'created_by', 'created_at']
    list_filter = ['environment']
    search_fields = ['name']

@admin.register(Baseline)
class BaselineAdmin(admin.ModelAdmin):
    list_display = ['id', 'item', 'environment', 'browser', 'device_profile', 'version', 'approved_by', 'approved_at']
    list_filter = ['environment', 'browser']
    search_fields = ['item__item_id']

@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'suite', 'environment', 'status', 'trigger_type', 'started_at', 'completed_at']
    list_filter = ['status', 'trigger_type', 'environment']

@admin.register(TestRunScript)
class TestRunScriptAdmin(admin.ModelAdmin):
    list_display = ['run', 'script_path', 'status', 'duration_ms', 'completed_at']
    list_filter = ['status']

@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ['id', 'run', 'analysis_type', 'status', 'issues_found', 'created_at']
    list_filter = ['status', 'analysis_type', 'issues_found']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'analysis', 'status', 'reviewer', 'reviewed_at']
    list_filter = ['status']

@admin.register(TestScript)
class TestScriptAdmin(admin.ModelAdmin):
    list_display = ['script_path', 'environment', 'item', 'assessment', 'test_type', 'category', 'updated_at']
    list_filter = ['environment', 'test_type', 'category']
    search_fields = ['script_path']

@admin.register(AISetting)
class AISettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'updated_at']

@admin.register(AITool)
class AIToolAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'category', 'enabled']
    list_filter = ['category', 'enabled']

@admin.register(TestDataSet)
class TestDataSetAdmin(admin.ModelAdmin):
    list_display = ['name', 'environment', 'assessment', 'data_type', 'created_at']
    list_filter = ['environment', 'data_type']
    search_fields = ['name']

@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'last_active_at']
