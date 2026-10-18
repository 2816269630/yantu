import { showFormError, values } from '../components/forms.js';
import { handleCommonAction } from './common-actions.js';
import { handleSessionAction, submitSessionForm } from './session-actions.js';
import { submitAssistantForm } from '../pages/assistant/actions.js';
import { handleMeetingAction, submitMeetingForm } from '../pages/collaboration/meeting-actions.js';
import {
  handleProgressAction,
  submitProgressForm,
} from '../pages/collaboration/progress-actions.js';
import { handleTaskAction, submitTaskForm } from '../pages/collaboration/task-actions.js';
import { handleDriveAction, submitDriveForm } from '../pages/drive/actions.js';
import { cloudAction } from '../pages/drive/browser.js';
import { handleHomeAction } from '../pages/home/actions.js';
import { handleLearningAction, submitLearningForm } from '../pages/learning/actions.js';
import { handleSettingsAction, submitSettingsForm } from '../pages/settings/actions.js';

const actionHandlers = {
  close: handleCommonAction,
  boot: handleCommonAction,
  refresh: handleCommonAction,
  'auth-login': handleSessionAction,
  'auth-register': handleSessionAction,
  logout: handleSessionAction,
  'settings-tab': handleSettingsAction,
  'create-team': handleSettingsAction,
  'accept-invite': handleSettingsAction,
  'invite-member': handleSettingsAction,
  'create-route': handleLearningAction,
  'edit-route': handleLearningAction,
  'route-versions': handleLearningAction,
  enroll: handleLearningAction,
  'adjust-plan': handleLearningAction,
  'plan-task': handleLearningAction,
  'create-task': handleTaskAction,
  'meeting-task': handleTaskAction,
  'task-progress': handleTaskAction,
  'submit-task': handleTaskAction,
  'review-submission': handleTaskAction,
  'create-experience': handleLearningAction,
  'edit-experience': handleLearningAction,
  bookmark: handleLearningAction,
  unbookmark: handleLearningAction,
  'create-meeting': handleMeetingAction,
  'edit-meeting': handleMeetingAction,
  'meeting-minutes': handleMeetingAction,
  'meeting-question': handleMeetingAction,
  'answer-meeting-question': handleMeetingAction,
  'meeting-complete': handleMeetingAction,
  'meeting-archive': handleMeetingAction,
  'upload-resource': handleDriveAction,
  'meeting-upload': handleDriveAction,
  'edit-resource': handleDriveAction,
  'resource-version': handleDriveAction,
  'download-version': handleDriveAction,
  'download-resource': handleDriveAction,
  'open-reader': handleDriveAction,
  'save-reading-page': handleDriveAction,
  'create-progress': handleProgressAction,
  'create-help': handleProgressAction,
  'comment-progress': handleProgressAction,
  'resolve-progress': handleProgressAction,
  'read-notification': handleHomeAction,
  'read-all': handleHomeAction,
  export: handleSettingsAction,
  'accept-handover': handleSettingsAction,
  'create-handover': handleSettingsAction,
  'member-role': handleSettingsAction,
  'remove-member': handleSettingsAction,
  'meeting-filter': handleMeetingAction,
  'resource-filter': handleDriveAction,
  'experience-filter': handleLearningAction,
  'task-tab': handleTaskAction,
  'route-filter': handleLearningAction,
  'open-team-settings': handleSettingsAction,
};
async function handleAction(action, id, source) {
  if (await cloudAction(action, id, source)) return;
  const handler = actionHandlers[action];
  if (handler) return handler(action, id, source);
}

const formHandlers = {
  setup: submitSessionForm,
  login: submitSessionForm,
  register: submitSessionForm,
  'create-team': submitSettingsForm,
  'accept-invite': submitSettingsForm,
  'invite-member': submitSettingsForm,
  route: submitLearningForm,
  'edit-route': submitLearningForm,
  'adjust-plan': submitLearningForm,
  'plan-task': submitLearningForm,
  task: submitTaskForm,
  'task-progress': submitTaskForm,
  submission: submitTaskForm,
  review: submitTaskForm,
  experience: submitLearningForm,
  'edit-experience': submitLearningForm,
  meeting: submitMeetingForm,
  'edit-meeting': submitMeetingForm,
  minutes: submitMeetingForm,
  'meeting-question': submitMeetingForm,
  'meeting-answer': submitMeetingForm,
  'resource-upload': submitDriveForm,
  'edit-resource': submitDriveForm,
  'resource-version': submitDriveForm,
  progress: submitProgressForm,
  'progress-comment': submitProgressForm,
  handover: submitSettingsForm,
  'member-role': submitSettingsForm,
  assistant: submitAssistantForm,
  profile: submitSettingsForm,
  team: submitSettingsForm,
};
async function handleSubmit(formElement) {
  const type = formElement.dataset.form,
    data = values(formElement),
    id = formElement.dataset.id;
  try {
    const handler = formHandlers[type];
    if (handler) await handler(type, data, id, formElement);
  } catch (error) {
    showFormError(formElement, error);
  }
}
export { handleAction, actionHandlers, handleSubmit, formHandlers };
