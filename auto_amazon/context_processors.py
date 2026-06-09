"""全站模板上下文。"""

from __future__ import annotations



from .wizard_jobs import get_active_job_for_user





def wizard_job_context(request):

    if not getattr(request, 'user', None) or not request.user.is_authenticated:

        return {'active_job': None}

    return {'active_job': get_active_job_for_user(request.user.id)}

