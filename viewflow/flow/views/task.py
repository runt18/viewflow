from django.utils.six.moves.urllib.parse import quote as urlquote

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.views import generic
from django.utils.http import is_safe_url
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from ...decorators import flow_view
from ..activation import ManagedViewActivation
from .base import (
    BaseTaskActionView, get_next_task_url, get_task_hyperlink,
    get_process_hyperlink
)


class ViewMixin(object):
    """
    Mixin for task views, that do not implement activation interface.
    """

    def get_context_data(self, **kwargs):
        context = super(ViewMixin, self).get_context_data(**kwargs)
        context['activation'] = self.activation
        return context

    def get_success_url(self):
        return get_next_task_url(self.request, self.activation.process)

    def get_template_names(self):
        flow_task = self.activation.flow_task
        opts = self.activation.flow_task.flow_cls._meta

        return (
            '{0}/{1}/{2}.html'.format(opts.app_label, opts.flow_label, flow_task.name),
            '{0}/{1}/task.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/task.html')

    def activation_done(self, *args, **kwargs):
        """Finish activation."""
        self.activation.done()

    def message_complete(self):
        hyperlink = get_task_hyperlink(self.activation.task, self.request.user)
        msg = _('Task {hyperlink} has been completed.').format(hyperlink=hyperlink)
        messages.success(self.request, mark_safe(msg), fail_silently=True)
        self.activation.process.refresh_from_db()

        if self.activation.process.finished:
            hyperlink = get_process_hyperlink(self.activation.process)
            msg = _('Process {hyperlink} has been completed.').format(hyperlink=hyperlink)
            messages.info(self.request, mark_safe(msg), fail_silently=True)

    def formset_valid(self, *args, **kwargs):
        """Called if base class is :class:`extra_views.FormsetView`."""
        super(ViewMixin, self).formset_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    def forms_valid(self, *args, **kwargs):
        """Called if base class is :class:`extra_views.InlinesView`."""
        super(ViewMixin, self).forms_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    def form_valid(self, *args, **kwargs):
        super(ViewMixin, self).form_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    @flow_view()
    def dispatch(self, request, activation, **kwargs):
        self.activation = activation

        if not activation.prepare.can_proceed():
            hyperlink = get_task_hyperlink(self.activation.task, self.request.user)
            msg = _('Task {hyperlink} cannot be executed.').format(hyperlink=hyperlink)
            messages.error(self.request, mark_safe(msg), fail_silently=True)
            return redirect(activation.flow_task.get_task_url(activation.task, url_type='details', user=request.user))

        if not self.activation.has_perm(request.user):
            raise PermissionDenied

        self.activation.prepare(request.POST or None)
        return super(ViewMixin, self).dispatch(request, **kwargs)


class ActivationViewMixin(object):
    """
    Mixin for views that implements activation interface.
    """

    def get_context_data(self, **kwargs):
        context = super(ActivationViewMixin, self).get_context_data(**kwargs)
        context['activation'] = self
        return context

    def get_template_names(self):
        flow_task = self.flow_task
        opts = self.flow_task.flow_cls._meta

        return (
            '{0}/{1}/{2}.html'.format(opts.app_label, opts.flow_label, flow_task.name),
            '{0}/{1}/task.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/task.html')

    def get_success_url(self):
        return get_next_task_url(self.request, self.process)

    def activation_done(self, *args, **kwargs):
        """Finish activation."""
        self.done()

    def message_complete(self):
        hyperlink = get_task_hyperlink(self.task, self.request.user)
        msg = _('Task {hyperlink} has been completed.').format(hyperlink=hyperlink)
        messages.success(self.request, mark_safe(msg), fail_silently=True)
        self.process.refresh_from_db()
        if self.process.finished:
            hyperlink = get_process_hyperlink(self.process)
            msg = _('Process {hyperlink} has been completed.').format(hyperlink=hyperlink)
            messages.info(self.request, mark_safe(msg), fail_silently=True)

    def formset_valid(self, *args, **kwargs):
        """Called if base class is :class:`extra_views.FormsetView`."""
        super(ActivationViewMixin, self).formset_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    def forms_valid(self, *args, **kwargs):
        """Called if base class is :class:`extra_views.InlineView`."""
        super(ActivationViewMixin, self).forms_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    def form_valid(self, *args, **kwargs):
        super(ActivationViewMixin, self).form_valid(*args, **kwargs)
        self.activation_done(*args, **kwargs)
        self.message_complete()
        return HttpResponseRedirect(self.get_success_url())

    @flow_view()
    def dispatch(self, request, *args, **kwargs):
        if not self.prepare.can_proceed():
            hyperlink = get_task_hyperlink(self.task, self.request.user)
            msg = _('Task {hyperlink} cannot be executed.').format(hyperlink=hyperlink)
            messages.error(request, mark_safe(msg), fail_silently=True)
            return redirect(self.flow_task.get_task_url(self.task, url_type='details', user=request.user))

        if not self.has_perm(request.user):
            raise PermissionDenied

        self.prepare(request.POST or None)
        return super(ActivationViewMixin, self).dispatch(request, *args, **kwargs)


class ProcessView(ManagedViewActivation, ActivationViewMixin, generic.UpdateView):
    fields = []

    @property
    def model(self):
        return self.flow_cls.process_cls

    def get_object(self, queryset=None):
        return self.process


class AssignView(ManagedViewActivation, generic.TemplateView):
    """
    Default assign view for flow task.

    Get confirmation from user, assigns task and redirects to task pages
    """

    def get_template_names(self):
        flow_task = self.flow_task
        opts = self.flow_task.flow_cls._meta

        return (
            '{0}/{1}/{2}_assign.html'.format(opts.app_label, opts.flow_label, flow_task.name),
            '{0}/{1}/task_assign.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/task_assign.html')

    def get_context_data(self, **kwargs):
        context = super(AssignView, self).get_context_data(**kwargs)
        context['activation'] = self
        return context

    def get_success_url(self):
        """Continue on task or redirect back to task list."""
        url = self.flow_task.get_task_url(self.task, url_type='guess', user=self.request.user)

        back = self.request.GET.get('back', None)
        if back and not is_safe_url(url=back, host=self.request.get_host()):
            back = '/'

        if '_continue' in self.request.POST and back:
            url = "{0}?back={1}".format(url, urlquote(back))
        elif back:
            url = back

        return url

    def post(self, request, *args, **kwargs):
        if '_assign' or '_continue' in request.POST:
            self.assign(self.request.user)
            hyperlink = get_task_hyperlink(self.task, request.user)
            msg = _('Task {hyperlink} has been assigned to {user}.').format(
                hyperlink=hyperlink, user=request.user.get_full_name())
            messages.info(request, mark_safe(msg), fail_silently=True)
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.get(request, *args, **kwargs)

    @flow_view()
    def dispatch(self, request, *args, **kwargs):
        if request.user is None or request.user.is_anonymous():
            raise PermissionDenied

        if not self.assign.can_proceed():
            hyperlink = get_task_hyperlink(self.task, request.user)
            msg = _('Task {hyperlink} cannot be assigned to {user}.').format(
                hyperlink=hyperlink, user=request.user.get_full_name())
            messages.error(request, mark_safe(msg), fail_silently=True)
            return redirect(self.flow_task.get_task_url(self.task, url_type='details', user=request.user))

        if not self.flow_task.can_assign(request.user, self.task):
            raise PermissionDenied

        return super(AssignView, self).dispatch(request, *args, **kwargs)


class UnassignView(BaseTaskActionView):
    action_name = 'unassign'

    def can_proceed(self):
        if self.activation.unassign.can_proceed():
            return self.activation.flow_task.can_unassign(self.request.user, self.activation.task)
        return False

    def perform(self):
        self.activation.unassign()
        hyperlink = get_task_hyperlink(self.activation.task, self.request.user)
        msg = _('Task {hyperlink} has been unassigned.').format(hyperlink=hyperlink)
        messages.info(self.request, mark_safe(msg), fail_silently=True)
