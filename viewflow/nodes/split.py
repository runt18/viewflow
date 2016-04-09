from .. import base, mixins
from ..activation import AbstractGateActivation
from ..exceptions import FlowRuntimeError
from ..token import Token


class SplitActivation(AbstractGateActivation):
    def __init__(self, **kwargs):
        self.next_tasks = []
        super(SplitActivation, self).__init__(**kwargs)

    def calculate_next(self):
        for node, cond in self.flow_task.branches:
            if cond:
                if cond(self.process):
                    self.next_tasks.append(node)
            else:
                self.next_tasks.append(node)

        if not self.next_tasks:
            raise FlowRuntimeError('No next task available for {0}'.format(self.flow_task.name))

    def activate_next(self):
        token_source = Token.split_token_source(self.task.token, self.task.pk)

        for n, next_task in enumerate(self.next_tasks, 1):
            next_task.activate(prev_activation=self, token=next(token_source))


class Split(mixins.TaskDescriptionMixin,
            mixins.DetailsViewMixin,
            mixins.UndoViewMixin,
            mixins.CancelViewMixin,
            mixins.PerformViewMixin,
            base.Gateway):

    task_type = 'SPLIT'
    activation_cls = SplitActivation

    def __init__(self, **kwargs):
        super(Split, self).__init__(**kwargs)
        self._activate_next = []

    def _outgoing(self):
        for next_node, cond in self._activate_next:
            edge_class = 'cond_true' if cond else 'default'
            yield base.Edge(src=self, dst=next_node, edge_class=edge_class)

    def _resolve(self, resolver):
        self._activate_next = \
            [(resolver.get_implementation(node), cond)
             for node, cond in self._activate_next]

    @property
    def branches(self):
        return self._activate_next

    def Next(self, node, cond=None):
        self._activate_next.append((node, cond))
        return self

    def Always(self, node):
        self._activate_next.append((node, None))
        return self
