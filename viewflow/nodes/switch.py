from .. import base, mixins
from ..activation import AbstractGateActivation
from ..exceptions import FlowRuntimeError


class SwitchActivation(AbstractGateActivation):
    def __init__(self, **kwargs):
        self.next_task = None
        super(SwitchActivation, self).__init__(**kwargs)

    def calculate_next(self):
        for node, cond in self.flow_task.branches:
            if cond:
                if cond(self.process):
                    self.next_task = node
                    break
            else:
                self.next_task = node

        if not self.next_task:
            raise FlowRuntimeError('No next task available for {0}'.format(self.flow_task.name))

    def activate_next(self):
        self.next_task.activate(prev_activation=self, token=self.task.token)


class Switch(mixins.TaskDescriptionMixin,
             mixins.DetailsViewMixin,
             mixins.UndoViewMixin,
             mixins.CancelViewMixin,
             mixins.PerformViewMixin,
             base.Gateway):

    task_type = 'SWITCH'
    activation_cls = SwitchActivation

    def __init__(self, **kwargs):
        super(Switch, self).__init__(**kwargs)
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

    def Case(self, node, cond=None):
        self._activate_next.append((node, cond))
        return self

    def Default(self, node):
        self._activate_next.append((node, None))
        return self
