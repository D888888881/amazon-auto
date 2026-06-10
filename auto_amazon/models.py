from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """扩展用户：记录注册审核状态（普通用户需超级管理员通过后方可登录）。"""

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已拒绝'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    registration_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_at = models.DateTimeField('审核时间', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='registration_reviews_done',
        verbose_name='审核人',
    )

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self) -> str:
        return f'{self.user.username} · {self.get_registration_status_display()}'


class AsinDashboardRow(models.Model):
    """上传分析后的 ASIN 行数据（每行一个 ASIN）。"""

    class FollowStatus(models.TextChoices):
        NORMAL = 'normal', '未关注'
        PRIORITY = 'priority', '重点关注'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_rows',
    )
    asin = models.CharField(max_length=32, db_index=True)
    profit_margin = models.FloatField('利润率(%)', null=True, blank=True)
    ranking_percent = models.FloatField('广告难度', null=True, blank=True)
    ops_difficulty_1 = models.TextField('运营难度1', blank=True)
    ops_difficulty_2 = models.TextField('运营难度2', blank=True)
    ops_difficulty_3 = models.TextField('运营难度3', blank=True)
    unit_purchase = models.FloatField('单价', null=True, blank=True)
    monthly_results = models.FloatField('体量', null=True, blank=True)
    profit_per_order = models.FloatField('利润额', null=True, blank=True)
    monthly_profit1 = models.FloatField('产品等级(原始值)', null=True, blank=True)
    monthly_sales_total = models.FloatField('月销售总额', null=True, blank=True)
    head_distance = models.FloatField('头程价格', null=True, blank=True)
    actual_cost = models.FloatField('成本', null=True, blank=True)
    head_actual_total = models.FloatField('成本+头程', null=True, blank=True)
    ad_removed_roi = models.FloatField('去广告投产比', null=True, blank=True)
    product_grade = models.CharField('产品等级', max_length=1)
    sales_trend_json = models.TextField('趋势 JSON', blank=True)
    exchange_rate = models.FloatField('汇率', null=True, blank=True)
    follow_status = models.CharField(
        '关注',
        max_length=16,
        choices=FollowStatus.choices,
        default=FollowStatus.NORMAL,
        db_index=True,
    )
    last_scheduled_roi_at = models.DateTimeField('上次定时ROI', null=True, blank=True, db_index=True)
    last_scheduled_ad_at = models.DateTimeField('上次定时广告难度', null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', 'asin']
        verbose_name = 'ASIN 分析行'
        verbose_name_plural = 'ASIN 分析行'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'asin'],
                name='uniq_asin_dashboard_user_asin',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.user_id}'


class AsinFolderAssignment(models.Model):
    """ASIN 文件夹（media/file/<ASIN>/）分配给哪些用户；由超级管理员维护。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    assignees = models.ManyToManyField(
        User,
        related_name='asin_folder_assignments',
        blank=True,
    )
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asin_folder_assignments_created',
        verbose_name='分配人',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASIN 文件夹分配'
        verbose_name_plural = 'ASIN 文件夹分配'

    def __str__(self) -> str:
        return self.asin


class AsinRoiPackVerification(models.Model):
    """用户在 Excel 中对某 ASIN 目录下 ROI-US-pack 表点击「确认校验」后记录；用于看板/数据审核展示「是否校验」。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    verified_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='roi_pack_verifications',
        verbose_name='确认人',
    )

    class Meta:
        verbose_name = 'ROI 表校验确认'
        verbose_name_plural = 'ROI 表校验确认'

    def __str__(self) -> str:
        return self.asin


class AsinDataUpdateStamp(models.Model):
    """记录 ASIN 数据最近一次更新时刻（每次重算都会刷新）。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASIN 数据更新时间'
        verbose_name_plural = 'ASIN 数据更新时间'

    def __str__(self) -> str:
        return self.asin


class ImportedMediaPath(models.Model):
    """记录用户通过数据审核导入到 media/file 下的路径（文件或目录）。"""

    # MySQL 唯一索引与 CharField 建议 <=255；常见 ASIN 相对路径足够
    rel_path = models.CharField(max_length=255, unique=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='imported_media_paths',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '导入文件路径'
        verbose_name_plural = '导入文件路径'

    def __str__(self) -> str:
        return self.rel_path


class AsinUploadBatch(models.Model):
    """一次 ASIN 文件上传记录（列表页每一行）。"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_upload_batches',
        verbose_name='上传用户',
    )
    source_filename = models.CharField('源文件名', max_length=255, blank=True)
    total_in_file = models.PositiveIntegerField('文件内 ASIN 数', default=0)
    new_count = models.PositiveIntegerField('新增 ASIN 数', default=0)
    skipped_count = models.PositiveIntegerField('跳过重复数', default=0)
    is_downloaded = models.BooleanField('是否已下载', default=False)
    downloaded_at = models.DateTimeField('下载时间', null=True, blank=True)
    downloaded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asin_batch_downloads',
        verbose_name='下载人',
    )
    created_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'ASIN 上传批次'
        verbose_name_plural = 'ASIN 上传批次'

    def __str__(self) -> str:
        return f'{self.user.username} · {self.new_count} · {self.created_at:%Y-%m-%d %H:%M}'


class AsinCatalogItem(models.Model):
    """全局 ASIN 库（用于上传去重）。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    batch = models.ForeignKey(
        AsinUploadBatch,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='所属批次',
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_catalog_items',
        verbose_name='上传用户',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', 'asin']
        verbose_name = 'ASIN 库条目'
        verbose_name_plural = 'ASIN 库条目'

    def __str__(self) -> str:
        return self.asin


class ScheduledJobLog(models.Model):
    """定时任务执行日志（便于排查稳定性问题）。"""

    class JobType(models.TextChoices):
        ROI = 'roi', 'ROI'
        AD_DIFFICULTY = 'ad_difficulty', '广告难度'
        COMBINED = 'combined', '组合'

    class Status(models.TextChoices):
        SUCCESS = 'success', '成功'
        PARTIAL = 'partial', '部分成功'
        FAILED = 'failed', '失败'
        SKIPPED = 'skipped', '跳过'

    job_type = models.CharField(max_length=32, choices=JobType.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    asin_list = models.JSONField(default=list, blank=True)
    detail = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at', '-id']
        verbose_name = '定时任务日志'
        verbose_name_plural = '定时任务日志'

    def __str__(self) -> str:
        return f'{self.get_job_type_display()} · {self.get_status_display()}'


class ScheduledTaskMessage(models.Model):
    """定时任务完成后推送给 ASIN 上传者的消息。"""

    class AlertStatus(models.TextChoices):
        NORMAL = 'normal', '未预警'
        ALERT = 'alert', '开始预警'
        ELIMINATE = 'eliminate', '立即淘汰'

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scheduled_task_messages',
        verbose_name='接收用户',
    )
    asin = models.CharField(max_length=32, db_index=True)
    dashboard_row = models.ForeignKey(
        AsinDashboardRow,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='schedule_messages',
    )
    curr_ad_roi = models.FloatField('当前去广告投产比', null=True, blank=True)
    curr_ad_difficulty = models.FloatField('当前广告难度', null=True, blank=True)
    curr_ops_difficulty = models.FloatField('当前运营难度', null=True, blank=True)
    latest_ad_roi = models.FloatField('最新去广告投产比', null=True, blank=True)
    latest_ad_difficulty = models.FloatField('最新广告难度', null=True, blank=True)
    latest_ops_difficulty = models.FloatField('最新运营难度', null=True, blank=True)
    delta_ad_roi = models.FloatField('对比去广告投产比', null=True, blank=True)
    delta_ad_difficulty = models.FloatField('对比广告难度', null=True, blank=True)
    delta_ops_difficulty = models.FloatField('对比运营难度', null=True, blank=True)
    delta_ad_roi_text = models.CharField(max_length=32, blank=True)
    delta_ad_difficulty_text = models.CharField(max_length=32, blank=True)
    delta_ops_difficulty_text = models.CharField(max_length=32, blank=True)
    alert_status = models.CharField(
        max_length=16,
        choices=AlertStatus.choices,
        default=AlertStatus.NORMAL,
    )
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    job_log = models.ForeignKey(
        ScheduledJobLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='messages',
    )

    class Meta:
        ordering = ['-sent_at', '-id']
        verbose_name = '定时任务消息'
        verbose_name_plural = '定时任务消息'

    def __str__(self) -> str:
        return f'{self.asin} → {self.recipient_id}'
