# library imports
from os import path, listdir
from datetime import datetime
from werkzeug import Response
from werkzeug.utils import redirect
# local imports
from baseController import BaseController, lookup, jsonify
from ..model import Task, UserTaskRoles, UserRoles, TaskStatus, TaskHistory, ForemanOptions, TaskType, TaskUpload
from ..utils.utils import multidict_to_dict, session, ROOT_DIR
from ..forms.forms import AssignInvestigatorForm, EditTaskUsersForm, EditTaskForm


class TaskController(BaseController):
    def _create_task_specific_breadcrumbs(self, task, case):
        self.breadcrumbs.append({'title': 'Cases', 'path': self.urls.build('case.view_all')})
        self.breadcrumbs.append({'title': case.case_name,
                                 'path': self.urls.build('case.view', dict(case_id=case.id))})
        self.breadcrumbs.append({'title': task.task_name,
                                 'path': self.urls.build('task.view', dict(case_id=case.id,
                                                                           task_id=task.id))})

    def view_all(self):
        self.check_permissions(self.current_user, 'Task', 'view-all')
        self.breadcrumbs.append({'title': 'Tasks', 'path': self.urls.build('task.view_all')})
        all_tasks = Task.get_active_tasks(user=self.current_user, case_perm_checker=self.check_permissions)
        user_primary_inv, user_secondary_inv = Task.get_tasks_assigned_to_user(user=self.current_user)
        return self.return_response('pages', 'view_tasks.html', all_tasks=all_tasks, user_primary_inv=user_primary_inv,
                                    user_secondary_inv=user_secondary_inv)

    def view_qas(self):
        self.check_permissions(self.current_user, 'Task', 'view-qas')
        self.breadcrumbs.append({'title': 'QAs', 'path': self.urls.build('task.view_qas')})
        completed = multidict_to_dict(self.request.args)
        if 'completed' in completed and completed['completed'] == "True":
            user_primary_qa, user_secondary_qa = Task.get_tasks_requiring_QA_by_user(user=self.current_user,
                                                                                     task_statuses=TaskStatus.qaComplete)
            completed = True
        else:
            user_primary_qa, user_secondary_qa = Task.get_tasks_requiring_QA_by_user(user=self.current_user)
            completed = False
        qa_tasks = Task.get_active_QAs(user=self.current_user, case_perm_checker=self.check_permissions)
        return self.return_response('pages', 'view_qas.html', qa_tasks=qa_tasks, user_primary_qa=user_primary_qa,
                                    user_secondary_qa=user_secondary_qa, completed=completed)

    def view(self, case_id, task_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'view')
            self._create_task_specific_breadcrumbs(task, task.case)
            return self.return_response('pages', 'view_task.html', task=task)
        else:
            return self.return_404()

    def view_upload(self, case_id, task_id, upload_id):
        upload = self._validate_upload(case_id, task_id, upload_id)
        if upload is not None:
            self.check_permissions(self.current_user, upload.task, 'add_file')
            self._create_task_specific_breadcrumbs(upload.task, upload.task.case)
            self.breadcrumbs.append({'title': upload.file_title,
                                     'path': self.urls.build('task.view_upload',
                                                             dict(case_id=upload.task.case.id,
                                                                  task_id=upload.task.id, upload_id=upload.id))})
            return self.return_response('pages', 'view_upload.html', upload=upload)
        else:
            return self.return_404()

    def delete_upload(self, case_id, task_id, upload_id):
        upload = self._validate_upload(case_id, task_id, upload_id)
        if upload is not None:
            self.check_permissions(self.current_user, upload.task, 'delete_file')
            self._create_task_specific_breadcrumbs(upload.task, upload.task.case)
            self.breadcrumbs.append({'title': upload.file_title,
                                     'path': self.urls.build('task.view_upload',
                                                             dict(case_id=upload.task.case.id,
                                                                  task_id=upload.task.id,
                                                                  upload_id=upload.id))})
            self.breadcrumbs.append({'title': "Delete",
                                     'path': self.urls.build('task.delete_upload',
                                                             dict(case_id=upload.task.case.id,
                                                                  task_id=upload.task.id, upload_id=upload.id))})
            closed = False
            confirm_close = multidict_to_dict(self.request.args)
            if 'confirm' in confirm_close and confirm_close['confirm'] == "true":
                upload.delete(self.current_user)
                closed = True

            return self.return_response('pages', 'delete_upload.html', upload=upload, closed=closed)
        else:
            return self.return_404()

    def change_status(self, case_id, task_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'edit')
            self._create_task_specific_breadcrumbs(task, task.case)
            self.breadcrumbs.append({'title': "Change Status",
                                     'path': self.urls.build('task.change_status', dict(case_id=task.case.id,
                                                                               task_id=task.id))})
            args = multidict_to_dict(self.request.args)
            change = False
            if "status" in args and args["status"] in TaskStatus.all_statuses:
                status = args["status"]
                if 'confirm' in args and args['confirm'] == "true":
                    task.set_status(status, self.current_user)
                    change = True
                return self.return_response('pages', 'confirm_task_status_change.html', task=task, change=change,
                                            status=status)
            else:
                return self.return_404(reason="The case or status change you are trying to make does not exist.")
        else:
            return self.return_404(reason="The case or status change you are trying to make does not exist.")

    def edit(self, task_id, case_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'edit')
            self._create_task_specific_breadcrumbs(task, task.case)
            self.breadcrumbs.append({'title': "Edit",
                                     'path': self.urls.build('task.edit', dict(case_id=task.case.id,
                                                                               task_id=task.id))})

            task_type_options = [(tt.id, tt.task_type) for tt in TaskType.get_all() if tt.task_type != "Undefined"]
            investigators = [(user.id, user.fullname) for user in UserRoles.get_investigators()]
            qas = [(user.id, user.fullname) for user in UserRoles.get_qas()]
            status_options = [(status, status) for status in TaskStatus.all_statuses]
            form_type = multidict_to_dict(self.request.args)
            active_tab = 0

            if 'form' in form_type and form_type['form'] == "edit_task":
                if self.validate_form(EditTaskForm()):
                    if task.task_name != self.form_result['task_name'] or task.task_type != self.form_result[
                        'task_type'] or task.background != self.form_result['background'] or task.location != \
                            self.form_result['location'] or self.form_result['deadline'] != task.deadline:
                        task.task_name = self.form_result['task_name']
                        task.task_type = self.form_result['task_type']
                        task.location = self.form_result['location']
                        task.background = self.form_result['background']
                        task.deadline = datetime.combine(self.form_result['deadline'], datetime.min.time()) if self.form_result['deadline'] != "" else None
                        task.add_change(self.current_user)
            elif 'form' in form_type and form_type['form'] == "edit_users":
                active_tab = 1
                if self.validate_form(EditTaskUsersForm()):
                    if task.principle_investigator != self.form_result['primary_investigator']:
                        self._create_new_user_role(UserTaskRoles.PRINCIPLE_INVESTIGATOR, task,
                                                   self.form_result['primary_investigator'])
                    if task.secondary_investigator != self.form_result['secondary_investigator']:
                        self._create_new_user_role(UserTaskRoles.SECONDARY_INVESTIGATOR, task,
                                                   self.form_result['secondary_investigator'])
                    if task.principle_QA != self.form_result['primary_qa']:
                        self._create_new_user_role(UserTaskRoles.PRINCIPLE_QA, task, self.form_result['primary_qa'])
                    if task.secondary_QA != self.form_result['secondary_qa']:
                        self._create_new_user_role(UserTaskRoles.SECONDARY_QA, task, self.form_result['secondary_qa'])

            task_history = self._get_tasks_history_changes(task)
            task_investigators_and_qa_history = self._get_investigators_and_qa_history_changes(task)
            principle_inv = task.principle_investigator.fullname if task.principle_investigator else "Please Select"
            secondary_inv = task.secondary_investigator.fullname if task.secondary_investigator else "Please Select"
            principle_qa = task.principle_QA.fullname if task.principle_QA else "Please Select"
            secondary_qa = task.secondary_QA.fullname if task.secondary_QA else "Please Select"
            return self.return_response('pages', 'edit_task.html', task=task, active_tab=active_tab,
                                        task_history=task_history,
                                        task_investigators_and_qa_history=task_investigators_and_qa_history,
                                        investigators=investigators, principle_inv=principle_inv, qas=qas,
                                        secondary_inv=secondary_inv, status_options=status_options,
                                        secondary_qa=secondary_qa, principle_qa=principle_qa,
                                        task_type_options=task_type_options, errors=self.form_error)
        else:
            return self.return_404()

    def close(self, task_id, case_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'close')
            self._create_task_specific_breadcrumbs(task, task.case)
            self.breadcrumbs.append({'title': "Close",
                                     'path': self.urls.build('task.close', dict(case_id=task.case.id,
                                                                                task_id=task.id))})

            closed = False
            confirm_close = multidict_to_dict(self.request.args)
            if 'confirm' in confirm_close and confirm_close['confirm'] == "true":
                task.close_task(self.current_user)
                closed = True

            return self.return_response('pages', 'confirm_close_task.html', task=task, closed=closed)
        else:
            return self.return_404(reason="The task you are trying to close does not exist.")

    def assign_work(self, case_id, task_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'assign-self')
            self._create_task_specific_breadcrumbs(task, task.case)
            self.breadcrumbs.append({'title': "Assign work to myself",
                                     'path': self.urls.build('task.assign_work', dict(case_id=task.case.id,
                                                                                      task_id=task.id))})

            if task.principle_investigator is not None and task.secondary_investigator is not None:
                return self.return_404()

            first_assignment = multidict_to_dict(self.request.args)
            if "confirm" in first_assignment and first_assignment["confirm"] == "true":
                if "assign" in first_assignment and first_assignment['assign'] == "primary":
                    if first_assignment['assign'] == "primary" and task.principle_investigator is not None:
                        return self.return_404()
                    else:
                        task.assign_task(self.current_user, True)
                        return self.return_response('pages', 'assign_task.html', task=task, success=True,
                                                    investigator=first_assignment['assign'])
                elif "assign" in first_assignment and first_assignment['assign'] == "secondary":
                    if first_assignment['assign'] == "secondary" and task.secondary_investigator is not None:
                        return self.return_404()
                    else:
                        task.assign_task(self.current_user, False)
                        return self.return_response('pages', 'assign_task.html', task=task, success=True,
                                                    investigator=first_assignment['assign'])
                else:
                    return self.return_404()
            else:
                if "assign" in first_assignment and (first_assignment['assign'] == "primary"
                                                     or first_assignment['assign'] == "secondary"):
                    if first_assignment['assign'] == "primary" and task.principle_investigator is not None:
                        return self.return_404()
                    elif first_assignment['assign'] == "secondary" and task.secondary_investigator is not None:
                        return self.return_404()
                    else:
                        return self.return_response('pages', 'assign_task.html', task=task, success=False,
                                                    investigator=first_assignment['assign'])
                else:
                    return self.return_404()
        else:
            return self.return_404()

    def assign_work_manager(self, case_id, task_id):
        task = self._validate_task(case_id, task_id)
        if task is not None:
            self.check_permissions(self.current_user, task, 'assign-other')
            self._create_task_specific_breadcrumbs(task, task.case)
            self.breadcrumbs.append({'title': "Assign investigator to task",
                                     'path': self.urls.build('task.assign_work_manager',
                                                             dict(case_id=task.case.id,
                                                                  task_id=task.id))})

            if task.principle_investigator is not None and task.secondary_investigator is not None:
                return self.return_404()

            if self.validate_form(AssignInvestigatorForm()):
                task.assign_task(self.form_result['investigator'], self.form_result['role'], self.current_user)
                if self.form_result['role']:
                    role_type = "Principle"
                else:
                    role_type = "Secondary"
                return self.return_response('pages', 'assign_task_manager.html', task=task, success=True,
                                            investigator=self.form_result['investigator'], role=role_type)
            else:
                roles = []

                if task.principle_investigator is None:
                    roles.append((UserTaskRoles.PRINCIPLE_INVESTIGATOR, UserTaskRoles.PRINCIPLE_INVESTIGATOR))
                if task.secondary_investigator is None:
                    roles.append((UserTaskRoles.SECONDARY_INVESTIGATOR, UserTaskRoles.SECONDARY_INVESTIGATOR))

                if task.principle_investigator is not None:
                    investigators = [(user.id, user.fullname) for user in UserRoles.get_investigators() if
                                     user.id != task.principle_investigator.id]
                elif task.secondary_investigator is not None:
                    investigators = [(user.id, user.fullname) for user in UserRoles.get_investigators() if
                                     user.id != task.secondary_investigator.id]
                else:
                    investigators = [(user.id, user.fullname) for user in UserRoles.get_investigators()]

                return self.return_response('pages', 'assign_task_manager.html', investigators=investigators,
                                            roles=roles, errors=self.form_error, task=task)
        else:
            return self.return_404()

    @staticmethod
    def _get_investigators_and_qa_history_changes(task):
        primary = UserTaskRoles.get_history(task, UserTaskRoles.PRINCIPLE_INVESTIGATOR)
        secondary = UserTaskRoles.get_history(task, UserTaskRoles.SECONDARY_INVESTIGATOR)
        primary_qa = UserTaskRoles.get_history(task, UserTaskRoles.PRINCIPLE_QA)
        secondary_qa = UserTaskRoles.get_history(task, UserTaskRoles.SECONDARY_QA)
        results = primary + secondary + primary_qa + secondary_qa
        results.sort(key=lambda d: d['date_time'])
        return results

    @staticmethod
    def _get_tasks_history_changes(task):
        history = TaskHistory.get_changes(task)
        status = TaskStatus.get_changes(task)
        uploads = TaskUpload.get_changes(task)
        results = history + status + uploads
        results.sort(key=lambda d: d['date_time'])
        return results

    def _create_new_user_role(self, role, task, form_result):
        try:
            user_role = UserTaskRoles.get_filter_by(task=task, role=role)[0]
            user_role.add_change(self.current_user, form_result)
            session.flush()
        except IndexError:
            if form_result is not True:
                new_role = UserTaskRoles(form_result, task, role)
                session.add(new_role)
                session.flush()
                new_role.add_change(self.current_user)