// Вспомогательная функция для сбора настроек из DOM (основного или модального)
export function getSettingsFromDOM(container = document) {
    const getVal = (selector) => container.querySelector(selector)?.value;
    const getChecked = (selector) => container.querySelector(selector)?.checked || false;

    const getContextFileRulesFromDOM = (cont) => {
        const rules = [];
        cont.querySelectorAll('.context-rule-item:not(.modal-only-template)').forEach(item => {
            const pattern = item.querySelector('.context-rule-pattern').value.trim();
            // Добавляем правило, только если поле шаблона не пустое
            if (pattern) {
                rules.push({
                    pattern: pattern,
                    prompt: item.querySelector('.context-rule-prompt').value,
                    enabled: item.querySelector('.context-rule-enabled').checked
                });
            }
        });
        return rules;
    };

    const getMeetingNameTemplatesFromDOM = (cont) => {
        const templates = [];
        cont.querySelectorAll('.meeting-name-template-item:not(.modal-only-template)').forEach(item => {
            const id = item.dataset.id;
            if (!id || id === 'null') return; // Пропускаем опцию "Не добавлять"

            const templateInput = item.querySelector('input.meeting-name-template-input');
            if (templateInput) { // Редактируемый шаблон
                templates.push({
                    id: id,
                    template: templateInput.value.trim()
                });
            } else { // Нередактируемый шаблон (например, сгенерированный)
                const label = item.querySelector('label');
                if (label) {
                    templates.push({ id: id, template: label.textContent.trim() });
                }
            }
        });
        return templates;
    };

    // Определяем, работаем ли мы в модальном окне, по наличию элемента с префиксом
    const isModal = container.id === 'confirmation-modal';
    const idPrefix = isModal ? '#modal-' : '#';

    return {
        use_custom_prompt: getChecked(`${idPrefix}use-custom-prompt`),
        prompt_addition: getVal(`${idPrefix}prompt-addition`),
        add_meeting_date: getChecked(`${idPrefix}add-meeting-date`),
        meeting_date_source: getVal('input[name="meeting_date_source"]:checked'), // name уникален, префикс не нужен
        active_meeting_name_template_id: getVal('input[name="active_meeting_name_template"]:checked'), // name уникален
        selected_contacts: [...container.querySelectorAll('.contact-group-list input[type="checkbox"]:checked')].map(cb => cb.value).filter(Boolean),
        context_file_rules: getContextFileRulesFromDOM(container),
        meeting_name_templates: getMeetingNameTemplatesFromDOM(container),
        confirm_prompt_on_action: getChecked(`${idPrefix}confirm-prompt-on-action`),
    };
}
