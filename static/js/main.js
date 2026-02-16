document.addEventListener('DOMContentLoaded', function () {
    // --- DOM Elements ---
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const statusTime = document.getElementById('status-time');
    const postProcessStatus = document.getElementById('post-process-status');
    const recBtn = document.getElementById('rec-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const favicon = document.getElementById('favicon');
    const volumeMetersContainer = document.querySelector('.volume-meters-container');

    // --- Tabs ---
    const tabLinks = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');

    tabLinks.forEach(link => {
        link.addEventListener('click', () => {
            const tabId = link.getAttribute('data-tab');

            tabLinks.forEach(l => l.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            link.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // --- Recording Status and Controls ---
    let currentStatus = 'stop';

    async function updateStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            currentStatus = data.status;
            statusTime.textContent = `(${data.time})`;

            // Update status indicator and text
            statusIndicator.className = 'status-indicator ' + data.status;
            switch (data.status) {
                case 'rec':
                    statusText.textContent = 'Запись';
                    volumeMetersContainer.classList.add('recording');
                    break;
                case 'pause':
                    statusText.textContent = 'Пауза';
                    volumeMetersContainer.classList.remove('recording');
                    break;
                case 'stop':
                default:
                    statusText.textContent = 'Остановлено';
                    volumeMetersContainer.classList.remove('recording');
                    break;
            }

            // Update control buttons state
            recBtn.disabled = data.status === 'rec';
            pauseBtn.disabled = data.status !== 'rec';
            stopBtn.disabled = data.status === 'stop';
            
            // Update favicon
            favicon.href = `/favicon.ico?v=${new Date().getTime()}`;

            // Update post-processing status
            if (data.post_processing.active) {
                postProcessStatus.textContent = data.post_processing.info;
                postProcessStatus.style.display = 'block';
            } else {
                postProcessStatus.style.display = 'none';
            }

        } catch (error) {
            console.error('Error fetching status:', error);
            statusText.textContent = 'Ошибка соединения';
            statusIndicator.className = 'status-indicator stop';
        }
    }

    // --- Audio Level Charts ---
    const audioChartCanvas = document.getElementById('audio-chart');
    const audioChartCtx = audioChartCanvas.getContext('2d');
    
    const chartHistorySize = 6000; // 300 секунд * 20 обновлений/сек = 6000 точек
    let micHistory = new Array(chartHistorySize).fill(0);
    let sysHistory = new Array(chartHistorySize).fill(0);

    function amplifyLevel(value) {
        // Используем квадратный корень для нелинейного усиления.
        // Это делает тихие звуки более заметными, не давая громким зашкаливать.
        return Math.sqrt(value);
    }

    let frameCount = 0;
    const scrollInterval = 3; // Сдвигать график каждый 3-й кадр, чтобы замедлить его

    function updateChartWithScroll() {
        const canvas = audioChartCanvas;
        const ctx = audioChartCtx;
        const { width, height } = canvas;
        const chartHeight = height - 25; // Увеличим место для подписей

        if (frameCount % scrollInterval === 0) {
            // 1. Сдвигаем существующее изображение влево на 1 пиксель
            const imageData = ctx.getImageData(1, 0, width - 1, height);
            ctx.putImageData(imageData, 0, 0);

            // 2. Очищаем последнюю колонку (1px), чтобы нарисовать там новые данные
            ctx.clearRect(width - 1, 0, 1, height);
        }

        // 3. Рисуем сетку и временные метки в последней колонке (которая только что была очищена)
        ctx.strokeStyle = '#ecf0f1';
        ctx.lineWidth = 0.5;
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';

        // Горизонтальные линии сетки (рисуем только в новой колонке)
        for (let i = 1; i < 4; i++) {
            const y = chartHeight * (i / 4);
            ctx.beginPath();
            ctx.moveTo(width - 1, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }

        // Вертикальная линия сетки и метка времени, когда наступает :00 или :30 секунд
        const now = new Date();
        const seconds = now.getSeconds();
        const milliseconds = now.getMilliseconds();
        
        // Проверяем, что мы находимся в начале секунды, чтобы нарисовать метку только один раз
        if ((seconds === 0 || seconds === 30) && milliseconds < (50 * scrollInterval)) {
            ctx.strokeStyle = '#bdc3c7'; // Более заметная линия сетки
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(width - 1, 0);
            ctx.lineTo(width - 1, chartHeight);
            ctx.stroke();

            // Рисуем метки времени для МСК и ИРК
            const mskTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow' });
            const irkTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk' });

            ctx.textAlign = 'right'; // Выравниваем по правому краю, чтобы текст не обрезался
            ctx.fillStyle = '#7f8c8d';
            ctx.fillText(`МСК: ${mskTime}`, width - 5, height - 15); // Рисуем у правого края
            ctx.fillText(`ИРК: ${irkTime}`, width - 5, height - 5);  // Рисуем у правого края
        }

        // 4. Рисуем новые сегменты линий
        ctx.lineWidth = 1.5;
        const drawNewSegment = (history, colorFunc) => {
            // Берем две последние точки из истории для отрисовки сегмента.
            // +1, т.к. history.length-1 это текущая точка, а нам нужна предыдущая.
            const prevValue = history[history.length - 2] || 0;
            const newValue = history[history.length - 1] || 0;

            ctx.beginPath();
            ctx.strokeStyle = colorFunc(newValue);
            // Рисуем новый сегмент в последнем пикселе холста
            ctx.moveTo(width - 1, chartHeight - (prevValue * chartHeight));
            ctx.lineTo(width, chartHeight - (newValue * chartHeight));
            ctx.stroke();
        };

        drawNewSegment(sysHistory, () => '#3498db');
        drawNewSegment(micHistory, value => value > 0.9 ? '#e74c3c' : (value > 0.7 ? '#f39c12' : '#2ecc71'));
    }

    async function updateAudioLevels() {
        try {
            const response = await fetch('/audio_levels');
            const levels = await response.json();

            // Add new level to history and remove the oldest
            const amplifiedMic = amplifyLevel(levels.mic < 0 ? 0 : levels.mic);
            const amplifiedSys = amplifyLevel(levels.sys < 0 ? 0 : levels.sys);

            micHistory.push(amplifiedMic);
            sysHistory.push(amplifiedSys);
            if (micHistory.length > chartHistorySize) micHistory.shift();
            if (sysHistory.length > chartHistorySize) sysHistory.shift();

            updateChartWithScroll();
            frameCount++;

        } catch (error) {
            // console.error('Error fetching audio levels:', error); // Keep this commented to avoid console spam
        }
    }

    recBtn.addEventListener('click', () => fetch(currentStatus === 'pause' ? '/resume' : '/rec'));
    pauseBtn.addEventListener('click', () => fetch('/pause'));
    stopBtn.addEventListener('click', () => {
        fetch('/stop');
        // Страница больше не перезагружается, чтобы не сбрасывать график.
        // Список записей обновится при следующем обновлении страницы вручную.
    });

    // --- Recordings List and Actions ---
    const recordingsListContainer = document.getElementById('recordings-list');

    // Сохраняем состояние развернутых групп
    let expandedGroups = new Set();

    // --- Оптимизированное обновление списка записей ---
    let lastRecordingsState = 0;

    async function checkForRecordingUpdates() {
        try {
            const response = await fetch('/recordings_state');
            const state = await response.json();
            if (state.last_modified > lastRecordingsState) {
                console.log('Обнаружены изменения в записях, обновляю список...');
                lastRecordingsState = state.last_modified;
                await updateRecordingsList();
            }
        } catch (error) {
            console.error('Ошибка при проверке состояния записей:', error);
        }
    }
    async function updateRecordingsList() {
        try {
            const response = await fetch('/get_date_dirs');
            const newDateGroups = await response.json();

            if (newDateGroups.length === 0 && recordingsListContainer.children.length === 0) {
                recordingsListContainer.innerHTML = '<p>Записей пока нет.</p>';
                return;
            }

            const existingGroupDates = new Set([...recordingsListContainer.querySelectorAll('.date-group')].map(el => el.dataset.date));
            const newGroupDates = new Set(newDateGroups.map(g => g.date));

            // Удаляем группы, которых больше нет
            existingGroupDates.forEach(date => {
                if (!newGroupDates.has(date)) {
                    recordingsListContainer.querySelector(`.date-group[data-date="${date}"]`)?.remove();
                }
            });

            // Добавляем новые группы или обновляем существующие развернутые
            for (const groupData of newDateGroups) {
                let groupEl = recordingsListContainer.querySelector(`.date-group[data-date="${groupData.date}"]`);
                if (!groupEl) {
                    // Создаем новую группу
                    groupEl = document.createElement('div');
                    groupEl.className = 'date-group collapsed';
                    groupEl.dataset.date = groupData.date;
                    groupEl.innerHTML = `
                        <h3>${groupData.formatted_date} <span>(${groupData.day_of_week})</span></h3>
                        <div class="recording-table">
                            <div class="recording-table-header">
                                <div class="recording-cell cell-time">Начало</div>
                                <div class="recording-cell cell-duration">Длительность</div>
                                <div class="recording-cell cell-title">Наименование</div>
                                <div class="recording-cell cell-files">Файлы</div>
                            </div>
                            <div class="recording-table-body"></div>
                        </div>`;
                    // Вставляем в правильное место (сохраняя сортировку по дате)
                    const nextGroup = Array.from(recordingsListContainer.children).find(child => child.dataset.date < groupData.date);
                    recordingsListContainer.insertBefore(groupEl, nextGroup || null);
                }

                // Если группа развернута, обновляем ее содержимое
                if (expandedGroups.has(groupData.date)) {
                    await loadRecordingsForGroup(groupEl, groupData.date);
                }
            }

        } catch (error) {
            console.error('Error updating recordings list:', error);
        }
    }

    async function loadRecordingsForGroup(groupEl, date) {
        const tableBody = groupEl.querySelector('.recording-table-body');
        tableBody.innerHTML = '<div class="loading-placeholder">Загрузка...</div>'; // Показываем индикатор загрузки

        try {
            const response = await fetch(`/get_recordings_for_date/${date}`);
            const recordings = await response.json();

            tableBody.innerHTML = ''; // Очищаем

            if (recordings.length === 0) {
                listEl.innerHTML = '<li class="loading-placeholder">В этой дате нет записей.</li>';
                return;
            }

            recordings.forEach(rec => {
                const audioExtension = rec.filename.split('.').pop().toUpperCase();
                const rowEl = document.createElement('div');
                rowEl.className = 'recording-table-row';
                rowEl.innerHTML = `
                    <div class="recording-cell cell-time">${rec.time}</div>
                    <div class="recording-cell cell-duration">${Math.floor(rec.duration / 60)} м ${Math.round(rec.duration % 60)} с</div>
                    <div class="recording-cell cell-title"><span class="editable-title" data-date="${date}" data-filename="${rec.filename}" data-prompt-addition="${escapeHtml(rec.promptAddition)}">${rec.title}</span></div>
                    <div class="recording-cell cell-files">
                        <a href="/files/${date}/${rec.filename}" target="_blank" class="action-btn audio-link">${audioExtension}</a>
                        <span class="file-action-pair">
                            <a href="/files/${date}/${rec.transcription_filename}" target="_blank" class="action-btn transcription-link ${rec.transcription_exists ? 'exists' : ''}">TXT</a>
                            <span class="recreate-actions-container"><button class="action-btn recreate-transcription-btn" title="Пересоздать транскрипцию" data-date="${date}" data-filename="${rec.filename}">&#x21bb;</button></span>
                        </span>
                        <span class="file-action-pair">
                            <a href="/files/${date}/${rec.protocol_filename}" target="_blank" class="action-btn protocol-link ${rec.protocol_exists ? 'exists' : ''}">PDF</a>
                            <span class="recreate-actions-container"><button class="action-btn recreate-protocol-btn" title="Пересоздать протокол" data-date="${date}" data-filename="${rec.filename}">&#x21bb;</button></span>
                        </span>
                    </div>
                `;
                tableBody.appendChild(rowEl);
            });
        } catch (error) {
            tableBody.innerHTML = '<div class="loading-placeholder">Ошибка загрузки записей.</div>';
            console.error(`Error loading recordings for ${date}:`, error);
        }
    }

    // Функция для экранирования HTML
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Используем делегирование событий для кнопок действий
    recordingsListContainer.addEventListener('click', (e) => {
        const target = e.target;

        // --- Обработчик для редактирования названия ---
        if (target.classList.contains('editable-title')) {
            const { date, filename, promptAddition } = target.dataset;
            const currentTitle = target.textContent;
            const row = target.closest('.recording-table-row');

            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentTitle;
            input.className = 'title-edit-input';

            target.replaceWith(input);
            input.focus();
            input.select();

            // Создаем и показываем блок с promptAddition
            let promptRow = null;
            if (promptAddition) {
                promptRow = document.createElement('div');
                promptRow.className = 'prompt-display-row';
                const promptContent = document.createElement('div');
                promptContent.className = 'prompt-addition-display';
                // Используем <pre> для сохранения форматирования и переносов строк
                promptContent.innerHTML = `<pre>${escapeHtml(promptAddition)}</pre>`;
                promptRow.appendChild(promptContent);

                // Вставляем новую строку после текущей строки записи
                row.parentNode.insertBefore(promptRow, row.nextSibling);
            }

            // --- Глобальный обработчик для выхода из режима редактирования ---
            const handleOutsideClick = (event) => {
                // Проверяем, был ли клик вне инпута, строки и блока с промптом
                const isClickInsideRow = row.contains(event.target);
                const isClickInsidePrompt = promptRow ? promptRow.contains(event.target) : false;

                if (!isClickInsideRow && !isClickInsidePrompt) {
                    saveTitle(); // Сохраняем и выходим из режима редактирования
                    // Удаляем обработчик после использования
                    document.removeEventListener('mousedown', handleOutsideClick);
                }
            };
            // Добавляем обработчик, когда входим в режим редактирования
            document.addEventListener('mousedown', handleOutsideClick);

            const saveTitle = async () => {
                const newTitle = input.value.trim();
                if (newTitle && newTitle !== currentTitle) {
                    // Обновляем data-атрибут, если нужно
                    target.dataset.promptAddition = promptAddition;
                    // Отправляем запрос на сервер
                    await fetch(`/update_metadata/${date}/${filename}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: newTitle })
                    });
                    target.textContent = newTitle;
                } else {
                    target.textContent = currentTitle;
                }
                input.replaceWith(target);
                if (promptRow) promptRow.remove();
                // Убедимся, что глобальный обработчик удален при выходе
                document.removeEventListener('mousedown', handleOutsideClick);
            };

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    input.blur();
                } else if (e.key === 'Escape') {
                    target.textContent = currentTitle;
                    if (promptRow) promptRow.remove();
                    // Убедимся, что глобальный обработчик удален при выходе
                    document.removeEventListener('mousedown', handleOutsideClick);
                    input.replaceWith(target);
                }
            });
        }

        const { date, filename } = target.dataset;
        if (target.classList.contains('recreate-transcription-btn')) {
            fetch(`/recreate_transcription/${date}/${filename}`);
            // Если мы были в режиме редактирования, выходим из него
            // Принудительно выходим из режима редактирования, если он был активен
            const input = target.closest('.recording-table-row').querySelector('.title-edit-input');
            if (input) input.blur();
            if (input) {
                // Вызываем blur(), чтобы сработал обработчик сохранения
                input.blur();
            }
            alert(`Задача пересоздания транскрипции для ${filename} отправлена.`);
        } else if (target.classList.contains('recreate-protocol-btn')) {
            fetch(`/recreate_protocol/${date}/${filename}`);
            // Если мы были в режиме редактирования, выходим из него
            // Принудительно выходим из режима редактирования, если он был активен
            const input = target.closest('.recording-table-row').querySelector('.title-edit-input');
            if (input) input.blur();
            if (input) {
                // Вызываем blur(), чтобы сработал обработчик сохранения
                input.blur();
            }
            alert(`Задача пересоздания протокола для ${filename} отправлена.`);
        } else if (target.closest('.date-group > h3')) {
        // Обработчик для разворачивания/сворачивания группы (теперь по клику на заголовок)
        const groupHeader = e.target.closest('.date-group > h3');
        if (groupHeader) {
            const groupEl = groupHeader.parentElement;
            const date = groupEl.dataset.date;
            groupEl.classList.toggle('collapsed');
            if (!groupEl.classList.contains('collapsed')) {
                expandedGroups.add(date);
                loadRecordingsForGroup(groupEl, date);
            } else {
                expandedGroups.delete(date);
            }
        }
    }
    });

    // --- Settings Tab ---
    const settingsForm = document.getElementById('settings-form');
    const settingsSaveStatus = document.getElementById('settings-save-status');
    const addContextRuleBtn = document.getElementById('add-context-rule-btn');
    const addMeetingDateCheckbox = document.getElementById('add-meeting-date');
    const meetingDateSourceGroup = document.getElementById('meeting-date-source-group');
    const meetingNameTemplatesContainer = document.getElementById('meeting-name-templates-container');
    const addMeetingNameTemplateBtn = document.getElementById('add-meeting-name-template-btn');

    async function loadSettings() {
        const response = await fetch('/get_web_settings');
        const settings = await response.json();
        document.getElementById('use-custom-prompt').checked = settings.use_custom_prompt;
        document.getElementById('prompt-addition').value = settings.prompt_addition;
        addMeetingDateCheckbox.checked = settings.add_meeting_date;
        const dateSourceRadio = document.querySelector(`input[name="meeting_date_source"][value="${settings.meeting_date_source}"]`);
        if (dateSourceRadio) dateSourceRadio.checked = true;

        renderMeetingNameTemplates(settings.meeting_name_templates, settings.active_meeting_name_template_id);
        toggleMeetingDateSourceVisibility();
    }

    function getContextFileRulesFromDOM() {
        const rules = [];
        document.querySelectorAll('.context-rule-item').forEach(item => {
            const pattern = item.querySelector('.context-rule-pattern').value.trim();
            const prompt = item.querySelector('.context-rule-prompt').value; // Не тримим, чтобы сохранить отступы
            const enabled = item.querySelector('.context-rule-enabled').checked;
            if (pattern && prompt) {
                rules.push({ pattern, prompt, enabled });
            }
        });
        return rules;
    }

    function getMeetingNameTemplatesFromDOM() {
        const templates = [];
        document.querySelectorAll('.meeting-name-template-item').forEach(item => {
            const id = item.dataset.id;
            const templateInput = item.querySelector('.meeting-name-template-input');
            if (id && templateInput) {
                const template = templateInput.value.trim();
                if (template) {
                    templates.push({ id, template });
                }
            }
        });
        return templates;
    }

    async function saveSettings() {
        // Собираем правила из DOM
        const contextFileRules = getContextFileRulesFromDOM();

        const settings = {
            use_custom_prompt: document.getElementById('use-custom-prompt').checked,
            prompt_addition: document.getElementById('prompt-addition').value,
            add_meeting_date: addMeetingDateCheckbox.checked,
            meeting_date_source: document.querySelector('input[name="meeting_date_source"]:checked').value,
            meeting_name_templates: getMeetingNameTemplatesFromDOM(),
            active_meeting_name_template_id: document.querySelector('input[name="active_meeting_name_template"]:checked')?.value || null,
            context_file_rules: contextFileRules,
            // selected_contacts сохраняются отдельно при изменении на их вкладке
        };

        const response = await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    
        // По запросу пользователя убираем уведомление о сохранении
        // const result = await response.json();
        // settingsSaveStatus.textContent = result.message;
        // settingsSaveStatus.style.color = response.ok ? 'green' : 'red';
        // setTimeout(() => settingsSaveStatus.textContent = '', 3000);
    }

    // Автосохранение при изменении настроек
    document.getElementById('use-custom-prompt').addEventListener('change', () => { saveSettings().then(updatePromptPreview); });
    // Для textarea используем 'change', чтобы не отправлять запрос на каждое нажатие клавиши
    document.getElementById('prompt-addition').addEventListener('change', () => { saveSettings().then(updatePromptPreview); }); 
    addMeetingDateCheckbox.addEventListener('change', () => {
        toggleMeetingDateSourceVisibility();
        saveSettings().then(updatePromptPreview);
    });
    document.querySelectorAll('input[name="meeting_date_source"]').forEach(radio => {
        radio.addEventListener('change', () => { saveSettings().then(updatePromptPreview); });
    });

    function toggleMeetingDateSourceVisibility() { meetingDateSourceGroup.style.display = addMeetingDateCheckbox.checked ? 'block' : 'none'; }

    // --- Context File Rules ---
    const contextRulesContainer = document.getElementById('context-file-rules-container');

    function renderContextFileRules(rules = []) {
        contextRulesContainer.innerHTML = '';
        if (rules.length === 0) {
            // Добавляем правило по умолчанию, если список пуст
            rules.push({ pattern: '*.html', prompt: '\n--- НАЧАЛО файла @{filename} ---\n{content}\n--- КОНЕЦ файла @{filename} ---\n', enabled: true });
        }
        rules.forEach(rule => {
            addContextRuleRow(rule.pattern, rule.prompt, rule.enabled);
        });
    }

    function addContextRuleRow(pattern = '', prompt = '', isEnabled = true) {
        const ruleItem = document.createElement('div');
        ruleItem.className = 'context-rule-item';

        ruleItem.innerHTML = `
            <div class="context-rule-header">
                <label class="context-rule-toggle">
                    <input type="checkbox" class="context-rule-enabled" ${isEnabled ? 'checked' : ''}>
                    Включено
                </label>
                <input type="text" class="context-rule-pattern" placeholder="Шаблон файла (e.g. *.html)" value="${pattern}">
                <button type="button" class="action-btn remove-rule-btn">&times;</button>
            </div>
            <textarea class="context-rule-prompt" rows="8" placeholder="Добавка к промпту...">${prompt}</textarea>
        `;

        ruleItem.querySelector('.remove-rule-btn').addEventListener('click', () => {
            ruleItem.remove();
            saveSettings().then(updatePromptPreview);
        });

        // Автосохранение при изменении полей
        ruleItem.querySelector('.context-rule-enabled').addEventListener('change', () => { saveSettings().then(updatePromptPreview); });
        ruleItem.querySelector('.context-rule-pattern').addEventListener('change', () => { saveSettings().then(updatePromptPreview); });
        ruleItem.querySelector('.context-rule-prompt').addEventListener('change', () => { saveSettings().then(updatePromptPreview); });

        contextRulesContainer.appendChild(ruleItem);
    }
    
    // --- Prompt Preview ---
    const promptPreviewContainer = document.getElementById('prompt-preview-container');
    const promptPreviewContent = document.getElementById('prompt-preview-content');

    async function updatePromptPreview() {
        try {
            const response = await fetch('/preview_prompt_addition');
            const data = await response.json();
            if (data.prompt_text) {
                promptPreviewContent.textContent = data.prompt_text;
                promptPreviewContainer.style.display = 'block';
            } else {
                promptPreviewContainer.style.display = 'none';
            }
        } catch (error) { console.error('Error fetching prompt preview:', error); }
    }

    

    addContextRuleBtn.addEventListener('click', () => {
        addContextRuleRow('', '', true);
    });

    // --- Meeting Name Templates ---
    function renderMeetingNameTemplates(templates = [], activeId = null) {
        meetingNameTemplatesContainer.innerHTML = '';

        // "Не добавлять" option
        const noneOption = createMeetingNameTemplateRow({ id: 'null', template: 'Не добавлять' }, activeId, false);
        meetingNameTemplatesContainer.appendChild(noneOption);

        templates.forEach(template => {
            const templateRow = createMeetingNameTemplateRow(template, activeId, true);
            meetingNameTemplatesContainer.appendChild(templateRow);
        });
    }

    function createMeetingNameTemplateRow(template, activeId, isEditable) {
        const item = document.createElement('div');
        item.className = 'meeting-name-template-item';
        item.dataset.id = template.id;

        const radioId = `template-radio-${template.id}`;
        const isChecked = template.id === activeId || (activeId === null && template.id === 'null');

        item.innerHTML = `
            <input type="radio" id="${radioId}" name="active_meeting_name_template" value="${template.id}" ${isChecked ? 'checked' : ''}>
            <label for="${radioId}" class="meeting-name-template-label"></label>
        `;

        const label = item.querySelector('label');
        if (isEditable) {
            label.innerHTML = `
                <input type="text" class="meeting-name-template-input" value="${template.template}">
                <button type="button" class="action-btn remove-rule-btn">&times;</button>
            `;
            const input = label.querySelector('input');
            const removeBtn = label.querySelector('button');

            input.addEventListener('change', () => { saveSettings(); updatePromptPreview(); });
            removeBtn.addEventListener('click', (e) => {
                e.preventDefault();
                item.remove();
                saveSettings().then(updatePromptPreview);
            });
        } else {
            label.textContent = template.template;
        }

        item.querySelector('input[type="radio"]').addEventListener('change', () => { saveSettings(); updatePromptPreview(); });

        return item;
    }

    addMeetingNameTemplateBtn.addEventListener('click', () => {
        const newId = `template-${Date.now()}`;
        const newTemplate = { id: newId, template: '' };
        const newRow = createMeetingNameTemplateRow(newTemplate, null, true);
        meetingNameTemplatesContainer.appendChild(newRow);
        // Focus on the new input
        newRow.querySelector('.meeting-name-template-input').focus();
    });


    settingsForm.addEventListener('submit', (e) => e.preventDefault()); // Предотвращаем стандартную отправку формы
    
    // --- Contacts Tab ---
    const contactsListContainer = document.getElementById('contacts-list-container');
    const newGroupNameInput = document.getElementById('new-group-name');
    const addGroupBtn = document.getElementById('add-group-btn');

    function setRandomGroupPlaceholder() {
        const adjectives = [
            'Лысый', 'Грустный', 'Танцующий', 'Летающий', 'Пьяный',
            'Поющий', 'Бегающий', 'Мечтающий', 'Злой', 'Спящий', 'Смеющийся',
            'Голодный', 'Задумчивый', 'Испуганный', 'Счастливый',
            'Прыгающий', 'Влюблённый', 'Уставший', 'Безумный',
            'Сердитый', 'Летающий задом наперёд', 'Танцующий ламбаду'
        ];

        const nouns = [
            // Все мужского рода
            'Хомяк', 'Пингвин', 'Картофель', 'Утюг', 'Кактус',
            'Огурец', 'Носок', 'Тапок', 'Холодильник', 'Чайник',
            'Ботинок', 'Банан', 'Пульт', 'Коврик', 'Батон',
            'Веник', 'Ёршик', 'Тазик', 'Кабачок', 'Бублик',
            'Робот', 'Ананас', 'Ниндзя', 'Монитор', 'Принтер'
        ];
        const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];
        const adjective = getRandomItem(adjectives);
        const noun = getRandomItem(nouns);

        newGroupNameInput.placeholder = `Новая группа: ${adjective} ${noun}`;
    }

    let contactsData = {};
    let selectedContactIds = [];

    async function loadContactsAndSettings() {
        const [contactsRes, settingsRes] = await Promise.all([fetch('/get_contacts'), fetch('/get_web_settings')]);
        contactsData = await contactsRes.json();
        const settings = await settingsRes.json();
        selectedContactIds = settings.selected_contacts || [];
        renderContacts();
        renderMeetingNameTemplates(settings.meeting_name_templates, settings.active_meeting_name_template_id);
        renderContextFileRules(settings.context_file_rules);
        updatePromptPreview();
        updateSelectedContactsCount();
    }

    function renderContacts() {
        contactsListContainer.innerHTML = '';

        if (!contactsData.groups || contactsData.groups.length === 0) {
            contactsListContainer.insertAdjacentHTML('beforeend', '<p>Список участников пуст. Создайте первую группу.</p>');
            return;
        }

        function generateRandomPlaceholder() {
            const names = ['Иван', 'Борис', 'Анна', 'Семён', 'Максим', 'Людмила', 'Геннадий', 'Ольга', 'Виктор', 'Наталья', 'Пётр', 'Зинаида', 'Руслан', 'Эльвира', 'Дмитрий', 'Клавдия', 'Аркадий', 'Татьяна', 'Юрий', 'Фёдор'];
            const patronymics = ['Вилкович', 'Борисович', 'Ананасович', 'Семёнович', 'Максимович', 'Люциферович', 'Генераторович', 'Огурцовович', 'Викторович', 'Носкович', 'Петрович', 'Закусонович', 'Рулетович', 'Эскимосович', 'Дмитриевич', 'Котлетович', 'Арбузович', 'Тапочкович', 'Юрьевич', 'Фёдорович'];
            const surnames = ['Ложкин', 'Бублик', 'Ананасов', 'Семечкин', 'Максимум', 'Лепёшкин', 'Глюкозов', 'Окрошка', 'Винегретов', 'Носков', 'Пельмёнов', 'Заливной', 'Рулетов', 'Эскимосов', 'Дырявин', 'Котлетов', 'Арбузов', 'Тапкин', 'Юморов', 'Фантазёров'];
            const positions = ['программист', 'бухгалтер', 'дизайнер', 'менеджер', 'аналитик', 'юрист', 'директор', 'редактор', 'тестировщик', 'администратор', 'инженер', 'маркетолог', 'консультант', 'куратор', 'архитектор', 'экономист', 'продюсер', 'секретарь', 'тренер', 'разработчик'];

            const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];

            const name = getRandomItem(names);
            const patronymic = getRandomItem(patronymics);
            const surname = getRandomItem(surnames);
            const position = getRandomItem(positions);

            // Корректируем окончание фамилии и отчества для женских имен
            let finalSurname = surname;
            let finalPatronymic = patronymic;
            if (['Анна', 'Людмила', 'Ольга', 'Наталья', 'Зинаида', 'Эльвира', 'Клавдия', 'Татьяна'].includes(name)) {
                if (surname.endsWith('ов') || surname.endsWith('ин') || surname.endsWith('ев')) {
                    finalSurname += 'а';
                }
                if (patronymic.endsWith('ич')) {
                    finalPatronymic = patronymic.slice(0, -2) + 'на';
                }
            }

            return `${finalSurname} ${name} ${finalPatronymic} — ${position}`;
        }

        // Сортируем группы по имени (алфавиту)
        const sortedGroups = [...contactsData.groups].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        sortedGroups.forEach(group => {
            const groupEl = document.createElement('div');
            // Добавляем класс 'collapsed', чтобы группа была свернута по умолчанию
            groupEl.className = 'contact-group collapsed';

            const groupHeaderEl = document.createElement('div');
            groupHeaderEl.className = 'contact-group-header';

            const groupHeaderLabel = document.createElement('label');
            groupHeaderLabel.className = 'contact-group-header-label'; // Новый класс для стилизации
            const groupNameEl = document.createElement('h4');
            groupNameEl.className = 'contact-group-name';
            groupNameEl.textContent = group.name;

            // Создаем обертку для иконки, чтобы увеличить кликабельную область
            const expandIconWrapper = document.createElement('div');
            expandIconWrapper.className = 'expand-icon-wrapper';

            // Создаем саму иконку
            const expandIcon = document.createElement('span');
            expandIcon.className = 'expand-icon';
            expandIconWrapper.appendChild(expandIcon);
            groupHeaderEl.appendChild(expandIconWrapper);

            groupNameEl.style.cursor = 'text'; // Указываем, что текст можно редактировать

            const groupCheckbox = document.createElement('input');
            groupCheckbox.value = "";
            groupCheckbox.type = 'checkbox';
            groupCheckbox.title = 'Выбрать/снять всех в группе';
            
            // --- Счетчик участников ---
            const contactIdsInGroup = group.contacts.map(c => c.id);
            const totalCount = contactIdsInGroup.length;
            const selectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;

            const groupCounterEl = document.createElement('span');
            groupCounterEl.className = 'group-counter';
            groupCounterEl.textContent = `${selectedCount} / ${totalCount}`;
            // --- Конец счетчика ---

            // Логика inline-редактирования для названия группы
            groupNameEl.addEventListener('click', () => {
                const oldName = group.name;
                const input = document.createElement('input');
                input.value = oldName;
                input.className = 'contact-name-edit'; // Используем тот же стиль, что и для участника

                // Скрываем счетчик при редактировании
                if (groupHeaderEl.contains(groupCounterEl)) groupHeaderEl.removeChild(groupCounterEl);

                // Заменяем h4 на input
                groupHeaderLabel.replaceChild(input, groupNameEl);
                input.focus();
                input.select();

                // Создаем и добавляем кнопку удаления группы
                const deleteGroupBtn = document.createElement('button');
                deleteGroupBtn.textContent = 'Удалить группу';
                deleteGroupBtn.className = 'action-btn delete-group-btn';
                deleteGroupBtn.onmousedown = (e) => { // Используем mousedown, чтобы сработало до blur
                    e.preventDefault(); // Предотвращаем потерю фокуса с инпута
                    deleteGroup(oldName);
                };
                groupHeaderEl.appendChild(deleteGroupBtn);

                const saveChanges = async () => {
                    const newName = input.value.trim();
                    // Удаляем кнопку и возвращаем счетчик
                    groupHeaderEl.removeChild(deleteGroupBtn);
                    groupHeaderEl.appendChild(groupCounterEl);

                    // Если имя не изменилось или пустое, просто возвращаем h4
                    if (newName === oldName || !newName) {
                        groupHeaderLabel.replaceChild(groupNameEl, input);
                        updateGroupCounter(); // Обновляем счетчик на всякий случай
                        return;
                    }
                    // Отправляем запрос на сервер
                    const response = await fetch(`/groups/update`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ old_name: oldName, new_name: newName })
                    });

                    if (response.ok) {
                        // При успехе перезагружаем список, чтобы все обновилось
                        loadContactsAndSettings();
                    } else {
                        const result = await response.json();
                        alert(`Ошибка: ${result.message}`);
                        groupHeaderLabel.replaceChild(groupNameEl, input); // Возвращаем старое имя в случае ошибки
                    }
                };

                input.addEventListener('blur', saveChanges);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        input.blur();
                    } else if (e.key === 'Escape') { 
                        // Возвращаем все как было
                        groupHeaderEl.appendChild(groupCounterEl);
                        groupHeaderEl.removeChild(deleteGroupBtn); // Удаляем кнопку
                        groupHeaderLabel.replaceChild(groupNameEl, input); // Возвращаем h4 без сохранения
                    }
                });
            });

            groupHeaderLabel.appendChild(groupCheckbox); // Чекбокс внутри label
            groupHeaderLabel.appendChild(groupNameEl);   // Имя группы внутри label

            groupHeaderEl.appendChild(groupHeaderLabel); // Label добавляется в заголовок
            groupHeaderEl.appendChild(groupCounterEl);   // Счетчик добавляется в заголовок
            groupEl.appendChild(groupHeaderEl);

            // Функция для обновления состояния группового чекбокса
            const updateGroupCheckboxState = () => {
                const checkedInGroup = contactIdsInGroup.filter(id => selectedContactIds.includes(id));
                groupCheckbox.checked = checkedInGroup.length === contactIdsInGroup.length && contactIdsInGroup.length > 0;
                groupCheckbox.indeterminate = checkedInGroup.length > 0 && checkedInGroup.length < contactIdsInGroup.length;
            };

            // Функция для обновления текста счетчика
            const updateGroupCounter = () => {
                const currentSelectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;
                groupCounterEl.textContent = `${currentSelectedCount} / ${totalCount}`;
            };

            // Обработчик для группового чекбокса
            groupCheckbox.addEventListener('change', () => {
                handleGroupCheckboxChange(groupCheckbox.checked, contactIdsInGroup, updateGroupCounter);
            });

            const listEl = document.createElement('ul');
            listEl.className = 'contact-group-list';

            // Добавляем строку для добавления нового участника в группу (в начало списка)
            const addItemEl = document.createElement('li');
            addItemEl.className = 'add-item-row';

            const addInput = document.createElement('input');
            addInput.type = 'text';
            addInput.placeholder = `Новый учасник: ${generateRandomPlaceholder()}`;
            addInput.className = 'add-item-input';
            const addBtn = document.createElement('button');
            addBtn.textContent = 'Добавить';
            addBtn.className = 'action-btn';
            addBtn.onclick = async () => {
                const name = addInput.value.trim();
                if (!name) {
                    alert('Имя участника не может быть пустым.');
                    return;
                }
                await fetch('/contacts/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, group_name: group.name })
                });
                addInput.value = '';
                loadContactsAndSettings(); // Перезагружаем список
            };
            addInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });

            addItemEl.appendChild(addInput);
            addItemEl.appendChild(addBtn);
            listEl.appendChild(addItemEl);

            // Сортируем контакты в группе по имени (алфавиту)
            const sortedContacts = [...group.contacts].sort((a, b) => a.name.localeCompare(b.name, 'ru'));

            sortedContacts.forEach(contact => {
                const itemEl = document.createElement('li');
                
                const labelEl = document.createElement('label');
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.value = contact.id;
                checkbox.checked = selectedContactIds.includes(contact.id);
                checkbox.addEventListener('change', () => {
                    saveContactSelection().then(updatePromptPreview); // Сохраняем выбор и обновляем предпросмотр
                    updateGroupCheckboxState(); // Обновляем состояние группового чекбокса
                    updateGroupCounter(); // Обновляем счетчик
                });

                labelEl.appendChild(checkbox);
                
                // Создаем span для имени, чтобы сделать его редактируемым
                const nameSpan = document.createElement('span');
                nameSpan.className = 'contact-name';
                nameSpan.textContent = contact.name;
                labelEl.appendChild(nameSpan);

                itemEl.appendChild(labelEl);

                listEl.appendChild(itemEl);

                // Логика inline-редактирования
                nameSpan.addEventListener('click', () => {
                    const currentName = nameSpan.textContent;
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.value = currentName;
                    input.className = 'contact-name-edit';

                    // Создаем кнопку удаления и контейнер для нее
                    const buttonsContainer = document.createElement('div');
                    buttonsContainer.className = 'item-actions';
                    const deleteBtn = document.createElement('button');
                    deleteBtn.textContent = 'Удалить';
                    deleteBtn.className = 'action-btn';
                    // Используем mousedown, чтобы событие сработало до blur на поле ввода
                    deleteBtn.onmousedown = (e) => {
                        e.preventDefault(); // Предотвращаем потерю фокуса с поля ввода
                        deleteContact(contact.id, contact.name);
                    };
                    buttonsContainer.appendChild(deleteBtn);

                    // Заменяем span на input
                    labelEl.replaceChild(input, nameSpan);
                    // Вставляем контейнер с кнопкой после label
                    itemEl.appendChild(buttonsContainer);
                    input.focus();
                    input.select();

                    const saveChanges = async () => {
                        const newName = input.value.trim();
                        // Удаляем кнопку удаления
                        itemEl.removeChild(buttonsContainer);
                        // Если имя не изменилось или пустое, просто возвращаем span
                        if (newName === currentName || !newName) {
                            labelEl.replaceChild(nameSpan, input);
                            return;
                        }

                        // Отправляем запрос на сервер
                        await fetch(`/contacts/update/${contact.id}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name: newName })
                        });

                        // Обновляем имя в span и возвращаем его
                        nameSpan.textContent = newName;
                        labelEl.replaceChild(nameSpan, input);
                    };

                    // Сохраняем при потере фокуса
                    input.addEventListener('blur', saveChanges);

                    // Сохраняем по Enter, отменяем по Escape
                    input.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter') {
                            input.blur();
                        } else if (e.key === 'Escape') {
                            // Удаляем кнопку и возвращаем span без сохранения
                            itemEl.removeChild(buttonsContainer);
                            labelEl.replaceChild(nameSpan, input);
                        }
                    });
                });
            });

            groupEl.appendChild(listEl);
            contactsListContainer.appendChild(groupEl);

            // Устанавливаем начальное состояние группового чекбокса
            updateGroupCheckboxState();

            // Обработчик для сворачивания/разворачивания только по клику на иконку
            expandIconWrapper.addEventListener('click', (e) => {
                e.stopPropagation(); // Предотвращаем всплытие события до других элементов
                groupEl.classList.toggle('collapsed');
            });

            // Добавляем такой же обработчик на счетчик, чтобы по нему тоже можно было сворачивать
            groupCounterEl.addEventListener('click', (e) => {
                e.stopPropagation(); // Предотвращаем всплытие события
                groupEl.classList.toggle('collapsed');
            });

            // Обработчик для клика по label (включая название группы), чтобы переключать чекбокс
            groupHeaderLabel.addEventListener('click', (e) => {
                // Игнорируем клики по самому чекбоксу (чтобы избежать двойного срабатывания) и полю редактирования
                if (e.target.tagName === 'INPUT' || e.target.classList.contains('contact-name-edit')) {
                    return;
                }

                // Определяем, нужно ли выбрать всех (true) или снять выбор (false).
                // Если выбраны не все (включая 0), то мы выбираем всех.
                // Если выбраны уже все, то мы снимаем выбор.
                const shouldBeChecked = groupCheckbox.indeterminate || !groupCheckbox.checked;
                handleGroupCheckboxChange(shouldBeChecked, contactIdsInGroup, updateGroupCounter);
            });
        });
    }

    function getSelectedContacts() {
        const selected = [];
        document.querySelectorAll('#contacts-list-container .contact-group-list li label input[type="checkbox"]:checked').forEach(cb => {
            // Убедимся, что у чекбокса есть значение (ID контакта), чтобы не считать групповые чекбоксы
            if (cb.value) {
                selected.push(cb.value);
            }
        });
        return selected;
    }

    async function saveContactSelection() {
        selectedContactIds = getSelectedContacts();
        updateSelectedContactsCount(); // Обновляем счетчик на вкладке
        const settings = { selected_contacts: selectedContactIds };

        // We only update the contacts, not the whole form
        await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    }
    
    // --- Функция для обновления счетчика на вкладке ---
    function updateSelectedContactsCount() {
        const countElement = document.getElementById('selected-contacts-count');
        if (countElement) {
            const count = selectedContactIds.length;
            countElement.textContent = count > 0 ? `(${count})` : '';
            // Добавим немного стиля, чтобы счетчик был заметнее
            countElement.style.color = '#3498db';
            countElement.style.fontWeight = 'normal';
        }
    }

    async function handleGroupCheckboxChange(isChecked, contactIdsInGroup, updateCounterCallback) {
        const groupCheckboxes = document.querySelectorAll(`input[type="checkbox"]`);
        let selectionChanged = false;
        groupCheckboxes.forEach(cb => {
            if (contactIdsInGroup.includes(cb.value)) {
                if (cb.checked !== isChecked) {
                    cb.checked = isChecked;
                    // Обновляем глобальный массив ID
                    selectionChanged = true;
                }
            }
        });

        // Сохраняем изменения, только если они были
        if (selectionChanged) await saveContactSelection();

        // Обновляем счетчик после всех изменений
        if (updateCounterCallback) updateCounterCallback();
    }

    addGroupBtn.addEventListener('click', async () => {
        const groupName = newGroupNameInput.value.trim();
        if (!groupName) {
            alert('Имя группы не может быть пустым.');
            return;
        }

        // Просто добавляем контакт с пустым именем, чтобы сервер создал группу
        await fetch('/contacts/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: `_init_group_`, group_name: groupName })
        });

        newGroupNameInput.value = '';
        loadContactsAndSettings();
    });

    async function loadGroupNames() {
        try {
            const response = await fetch('/get_group_names');
            const groupNames = await response.json();
            const datalist = document.getElementById('group-names-list');
            if (datalist) {
                datalist.innerHTML = ''; // Очищаем старые опции
                groupNames.forEach(name => {
                    datalist.innerHTML += `<option value="${name}">`;
                });
            }
        } catch (error) { console.error('Error fetching group names:', error); }
    }

    async function deleteContact(id, name) {
        if (!confirm(`Вы уверены, что хотите удалить участника "${name}"?`)) {
            return;
        }
        await fetch(`/contacts/delete/${id}`, { method: 'POST' });
        loadContactsAndSettings();
    }

    async function deleteGroup(name) {
        if (!confirm(`Вы уверены, что хотите удалить группу "${name}" и всех ее участников?`)) {
            return;
        }
        await fetch(`/groups/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        loadContactsAndSettings();
    }

    newGroupNameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            addGroupBtn.click();
        }
    });

    // --- Initialization ---
    function initialize() {
        updateStatus();
        setInterval(updateStatus, 2000); // Poll status every 2 seconds
        setInterval(checkForRecordingUpdates, 3000); // Проверяем наличие обновлений каждые 3 секунды
        setInterval(updateAudioLevels, 50); // Уменьшаем интервал для большей плавности (20 FPS)
        loadSettings();
        updatePromptPreview();
        loadContactsAndSettings();
        setRandomGroupPlaceholder();
    }

    initialize();
});