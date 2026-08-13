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

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_rows',
    )
    asin = models.CharField(max_length=32, db_index=True)
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
    )
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
                fields=['user', 'asin', 'marketplace'],
                name='uniq_asin_dashboard_user_asin_marketplace',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.marketplace} · {self.user_id}'


class AsinFolderAssignment(models.Model):
    """ASIN 文件夹分配（历史表；产品已取消分配门控，保留以免丢数据）。"""

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
    """用户对某站点 ASIN 的 ROI 校验（按人独立；看板展示所有已校验用户）。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='roi_pack_verifications',
        verbose_name='校验人',
    )
    asin = models.CharField(max_length=32, db_index=True)
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
    )
    verified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ROI 表校验确认'
        verbose_name_plural = 'ROI 表校验确认'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'asin', 'marketplace'],
                name='uniq_roi_verify_user_asin_mp',
            ),
        ]
        indexes = [
            models.Index(fields=['asin', 'marketplace'], name='idx_roi_verify_asin_mp'),
            models.Index(fields=['user', 'marketplace'], name='idx_roi_verify_user_mp'),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.marketplace} · {self.user_id}'


class AsinPassedFlag(models.Model):
    """ASIN 已通过标记（全局：一人标记，全员可见）。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    asin = models.CharField(max_length=32, db_index=True)
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
    )
    passed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asin_passed_flags',
        verbose_name='标记人',
    )
    passed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASIN 已通过'
        verbose_name_plural = 'ASIN 已通过'
        constraints = [
            models.UniqueConstraint(
                fields=['asin', 'marketplace'],
                name='uniq_asin_passed_asin_mp',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.marketplace}'


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
    """记录用户通过数据审核导入到 media/file 下的路径（文件或目录），按站点区分。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    # MySQL 唯一索引与 CharField 建议 <=255；常见 ASIN 相对路径足够
    rel_path = models.CharField(max_length=255, db_index=True)
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='imported_media_paths',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '导入文件路径'
        verbose_name_plural = '导入文件路径'
        constraints = [
            models.UniqueConstraint(
                fields=['rel_path', 'marketplace'],
                name='uniq_imported_media_path_marketplace',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.rel_path} · {self.marketplace}'


class MarketplaceAsinRoot(models.Model):
    """站点 × ASIN 根目录物化表（导入时维护，供看板/ROI/审核快速查询）。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        db_index=True,
    )
    asin = models.CharField(max_length=32, db_index=True)
    first_imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '站点 ASIN 根'
        verbose_name_plural = '站点 ASIN 根'
        constraints = [
            models.UniqueConstraint(
                fields=['marketplace', 'asin'],
                name='uniq_marketplace_asin_root',
            ),
        ]
        indexes = [
            models.Index(fields=['marketplace', 'asin'], name='idx_mp_asin_root_mp_asin'),
        ]

    def __str__(self) -> str:
        return f'{self.marketplace} · {self.asin}'


class AsinUploadBatch(models.Model):
    """一次 ASIN 文件上传记录（列表页每一行）。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_upload_batches',
        verbose_name='上传用户',
    )
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
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
        return f'{self.user.username} · {self.marketplace} · {self.new_count} · {self.created_at:%Y-%m-%d %H:%M}'


class AsinCatalogItem(models.Model):
    """按站点去重的 ASIN 库（用于上传去重）。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    asin = models.CharField(max_length=32, db_index=True)
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        default=Marketplace.US,
        db_index=True,
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=['asin', 'marketplace'],
                name='uniq_asin_catalog_asin_marketplace',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.marketplace}'


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


class RoiSiteConfig(models.Model):
    """自动 ROI 按站点的定值与节流参数。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        unique=True,
        db_index=True,
    )
    platform_commission = models.FloatField('平台佣金(%)', default=15.0)
    default_refund_rate = models.FloatField('默认退款率(%)', default=10.0)
    default_fba_fee = models.FloatField('默认FBA($)', default=5.0)
    default_unit_purchase = models.FloatField('默认采购价(￥)', default=10.0)
    batch_size = models.PositiveIntegerField('批大小', default=20)
    asin_delay_min_sec = models.FloatField('ASIN间隔最小秒', default=1.0)
    asin_delay_max_sec = models.FloatField('ASIN间隔最大秒', default=3.0)
    batch_delay_min_sec = models.FloatField('批间隔最小秒', default=4.0)
    batch_delay_max_sec = models.FloatField('批间隔最大秒', default=8.0)
    max_ban_rotations_per_run = models.PositiveIntegerField('单次跑最大换号次数', default=30)
    consecutive_fail_pause = models.PositiveIntegerField('连续失败暂停阈值', default=10)
    max_ban_retries_per_asin = models.PositiveIntegerField('单ASIN禁号重试', default=3)
    exchange_rate_override = models.FloatField('汇率覆盖', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ROI 站点定值'
        verbose_name_plural = 'ROI 站点定值'

    def __str__(self) -> str:
        return f'{self.marketplace} · 佣金{self.platform_commission}%'


class RoiAutoRun(models.Model):
    """一次自动 ROI 长跑任务。"""

    class Marketplace(models.TextChoices):
        US = 'US', '美国站'
        UK = 'UK', '英国站'

    class Status(models.TextChoices):
        RUNNING = 'running', '运行中'
        PAUSED = 'paused', '已暂停'
        STOPPED = 'stopped', '已停止'
        DONE = 'done', '已完成'
        ERROR = 'error', '出错'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='roi_auto_runs',
    )
    marketplace = models.CharField(
        '站点',
        max_length=8,
        choices=Marketplace.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    total = models.PositiveIntegerField(default=0)
    succeeded = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    current_asin = models.CharField(max_length=32, blank=True)
    last_account = models.CharField(max_length=128, blank=True)
    parity = models.FloatField('汇率', default=7.2)
    done_asins = models.JSONField(default=list, blank=True)
    ban_rotations = models.PositiveIntegerField(default=0)
    consecutive_fails = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    rq_job_id = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at', '-id']
        verbose_name = '自动 ROI 任务'
        verbose_name_plural = '自动 ROI 任务'
        indexes = [
            models.Index(fields=['user', 'marketplace', 'status'], name='idx_roi_auto_user_mp_st'),
        ]

    def __str__(self) -> str:
        return f'#{self.pk} · {self.marketplace} · {self.status}'


class RoiAutoRunLog(models.Model):
    """自动 ROI 逐 ASIN 详细日志。"""

    class Status(models.TextChoices):
        SUCCESS = 'success', '成功'
        FAILED = 'failed', '失败'
        RETRY = 'retry', '重试'
        BANNED_ROTATED = 'banned_rotated', '禁号换号'

    run = models.ForeignKey(
        RoiAutoRun,
        on_delete=models.CASCADE,
        related_name='logs',
    )
    asin = models.CharField(max_length=32, db_index=True)
    seq = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices)
    attempt = models.PositiveIntegerField(default=1)
    account_username = models.CharField(max_length=128, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_summary = models.CharField(max_length=500, blank=True)
    error_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '自动 ROI 日志'
        verbose_name_plural = '自动 ROI 日志'

    def __str__(self) -> str:
        return f'{self.asin} · {self.status}'
