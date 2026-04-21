from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('dashboard/export/', views.dashboard_export_excel, name='dashboard_export_excel'),

    path('dashboard/ops-filter/', views.dashboard_ops_filter, name='dashboard_ops_filter'),

    path(
        'pending-registrations/',views.pending_registrations,name='pending_registrations'),

    path('users/', views.user_management, name='user_management'),

    path('upload/start/', views.upload_start, name='upload_start'),
    path('upload/status/<uuid:job_id>/', views.upload_job_status, name='upload_job_status'),
    path('upload/', views.upload_page, name='upload'),
    path('compute-roi/', views.compute_roi_page, name='compute_roi'),
    path('fetch-data/', views.fetch_data_page, name='fetch_data'),

    path('excel/', views.excel_page, name='excel'),

    path('excel/edit/', views.excel_editor_page, name='excel_editor'),

    path('excel/browse/', views.excel_browse, name='excel_browse'),

    path('excel/download/', views.excel_download, name='excel_download'),

    path('excel/delete/', views.excel_delete, name='excel_delete'),

    path('excel/batch_download/', views.excel_batch_download, name='excel_batch_download'),

    path('excel/import/chunk/', views.excel_import_chunk, name='excel_import_chunk'),
    path('excel/import/commit/', views.excel_import_commit, name='excel_import_commit'),

    path('excel/load_media/', views.excel_load_media, name='excel_load_media'),

    path('excel/save_media/', views.excel_save_media, name='excel_save_media'),
    path('excel/import_data_origin/', views.excel_import_data_origin, name='excel_import_data_origin'),

    path('excel/recalc_roi_media/', views.excel_recalc_roi_media, name='excel_recalc_roi_media'),

    path('excel/confirm_roi_verify/', views.excel_confirm_roi_verify, name='excel_confirm_roi_verify'),

    path('excel/assign/', views.excel_assign_folders, name='excel_assign_folders'),

    path('excel/load/', views.excel_load, name='excel_load'),

    path('excel/save/', views.excel_save, name='excel_save'),
]
