from os import getenv

import boto3
from botocore.exceptions import ClientError

from taskbox.taskbase import exception
from taskbox.taskbase import task
from taskbox import user_task # noqa


class TaskManager():
    '''TaskManager'''

    def __init__(self, task_name) -> None:
        if task_name not in task.Task.task_dict:
            raise FileNotFoundError
        self.task_name = task_name
        self._task_info = None
        self._task_inst = None


    @property
    def task_info(self):
        if not self._task_info:
            self._task_info = task.Task.get_by_name(self.task_name)
        return self._task_info

    @property
    def task_inst(self):
        if not self._task_inst:
            task_cls = task.Task.task_dict.get(self.task_name)
            if not task_cls:
                raise ModuleNotFoundError
            self._task_inst = task_cls(**self.task_info)
        return self._task_inst

    def get_dict_info(self):
        '''display task info

        if task have multi config, we should return multi task history
        :return: OrderedDict() with task info
        '''
        return self.task_inst.info_format

    def pause(self):
        # TODO
        task.Task.get_by_name(self.task_name)
        pass

    def update_scheduler(self, req):
        # create/update/delete a scheduler, the name is taskname,
        task = self.task_inst
        expression = req.body.get('scheduler')

        try:
            # Delete
            if 'delete' in req.body:
                if 'expression' in task.scheduler:
                    task.scheduler.pop('expression')
                Eventscheduler().delete_scheduler(name=task.name)
                task.status = 'pause'

            # Update
            elif 'expression' in task.scheduler:
                task.scheduler = {'expression': expression}
                Eventscheduler().update_schedule(name=task.name,
                                                ScheduleExpression=expression)
                req.msg = ('success', f'Update scheduler success: {expression}')
            # Create
            else:
                task.scheduler = {'expression': expression}
                Eventscheduler().create(name=task.name,
                                            ScheduleExpression=expression)
                if len(self.task_inst.conf) != 0:
                    self.task_inst.status = 'normal'
                req.msg = ('success', f'Create scheduler success: {expression}')
        except ClientError as e:
            req.msg = (f'warning', f'Failed: {e}')

    def update_config(self, req):
        acc = req.body.pop('taskbox_conf_name')
        if not acc:
            raise exception.TaskConfigInvalid('配置名称是必须的！')
        if 'delete' in req.body:
            self.task_inst.conf.pop(acc)
            if len(self.task_inst.conf) == 0:
                self.task_inst.status = 'pending'
        else:
            self.task_inst.set_conf(acc, req.body)
            if self.task_inst.scheduler:
                self.task_inst.status = 'normal'
        req.msg = ('success', 'Success!')

    def run(self):
        self.task_inst.run()


class Eventscheduler():

    def __init__(self) -> None:
        self.func_arn = getenv('FUNC_ARN')
        self.role_arn = getenv('ROLE_ARN')
        self.client = boto3.client('scheduler')

    def create(self, name=None, ScheduleExpression=None):
        '''Create Eventbridge scheduler

        :param ScheduleExpression: string
            at(yyyy-mm-ddThh:mm:ss)
            rate(unit value)
            cron(minutes hours day_of_month month day_of_week year)
        :return: resp
        '''
        try:
            resp = self.client.create_schedule(
                Name=name,
                ScheduleExpression=ScheduleExpression,
                ScheduleExpressionTimezone='Asia/Shanghai',
                FlexibleTimeWindow={
                    'Mode': 'OFF',
                },
                Target={
                    'Arn': self.func_arn,
                    'RoleArn': self.role_arn,
                    'Input': '{"Excutetask": "%s"}' % name,
                },
                # Cloudfoundtion will create exc role with func logical name
                # RoleArn=getenv('ROLE_ARN'),
            )
        except ClientError as e:
            raise e
        return resp

    def update_schedule(self, name=None, ScheduleExpression=None):
        self.client.update_schedule(
            Name=name,
            ScheduleExpression=ScheduleExpression,
            ScheduleExpressionTimezone='Asia/Shanghai',
            FlexibleTimeWindow={
                'Mode': 'OFF',
            },
            Target={
                'Arn': self.func_arn,
                'RoleArn': self.role_arn,
                'Input': '{"Excutetask": "%s"}' % name,
            },
            # Cloudfoundtion will create exc role with func logical name
            # RoleArn=getenv('ROLE_ARN'),
        )

    def list_schedules(self):
        pass

    def delete_scheduler(self, name):
        self.client.delete_schedule(Name=name)
