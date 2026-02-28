import { recordingsListContainer } from '../dom.js';
import { showConfirmationModal } from './modal.js';

let expandedGroups = new Set();
let lastRecordingsState = 0;
let updatesIntervalId = null;
let isUpdatesPaused = false;

// Function to escape HTML special characters
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&#039;");
}

async function loadRecordingsForGroup(groupEl, date) {
    const tableBody = groupEl.querySelector('.recording-table-body');
    if (!tableBody) return;
    tableBody.innerHTML = '<div class="loading-placeholder">Загрузка...</div>';

    try {
        const response = await fetch(`/get_recordings_for_date/${date}`);
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        const recordings = await response.json();

        tableBody.innerHTML = '';

        if (recordings.length === 0) {
            tableBody.innerHTML = '<div class="loading-placeholder">В этой дате нет записей.</div>';
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
                        <span class="delete-action-container"><button class="action-btn delete-recording-btn" title="Удалить запись" data-date="${date}" data-filename="${rec.filename}">&#x1f5d1;</button></span>
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

async function updateRecordingsList() {
    if (!recordingsListContainer) return;
    try {
        const response = await fetch('/get_date_dirs');
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        const dateGroupsData = await response.json();

        if (dateGroupsData.length === 0 && recordingsListContainer.children.length === 0) {
            recordingsListContainer.innerHTML = '<p>Записей пока нет.</p>';
            return;
        }

        const weeks = {};
        dateGroupsData.forEach(group => {
            const weekId = group.week_header_text; // Use the full header text as a unique key
            if (!weeks[weekId]) weeks[weekId] = { header_text: group.week_header_text, dates: [] };
            weeks[weekId].dates.push(group);
        });

        recordingsListContainer.innerHTML = '';

        // Sort weeks by the latest date within each week group, in descending order.
        const sortedWeekKeys = Object.keys(weeks).sort((a, b) => {
            const lastDateA = weeks[a].dates.reduce((latest, curr) => curr.date > latest ? curr.date : latest, '0000-00-00');
            const lastDateB = weeks[b].dates.reduce((latest, curr) => curr.date > latest ? curr.date : latest, '0000-00-00');
            return lastDateB.localeCompare(lastDateA);
        });

        for (const [index, weekId] of sortedWeekKeys.entries()) {
            const weekData = weeks[weekId];
            const weekGroupEl = document.createElement('div');
            weekGroupEl.className = 'week-group';
            weekGroupEl.dataset.weekId = weekId;

            
            if (index > 0) {
                weekGroupEl.classList.add('collapsed');
            }

            const headerParts = (weekData.header_text || '').split(' : ');
            const weekDateRange = headerParts[0] || '';
            const weekNumberText = headerParts[1] || '';
            weekGroupEl.innerHTML = `<h4><span class="expand-icon"></span><span class="week-title">${weekDateRange}</span><span class="week-number">${weekNumberText}</span></h4>`;

            recordingsListContainer.appendChild(weekGroupEl);

            weekData.dates.sort((a, b) => a.date.localeCompare(b.date));
            
            for (const groupData of weekData.dates) {
                let groupEl = document.createElement('div');
                groupEl.className = 'date-group';
                if (expandedGroups.has(groupData.date)) {
                    groupEl.classList.remove('collapsed');
                } else {
                    groupEl.classList.add('collapsed');
                }
                groupEl.dataset.date = groupData.date;
                groupEl.innerHTML = `
                    <h3>
                        <div class="date-group-left">
                            <span class="expand-icon"></span><span class="date-group-title">${groupData.date_part}</span>
                        </div>
                        <span class="date-group-day">${groupData.day_of_week}</span>
                    </h3>
                `;
                
                const tableContainer = document.createElement('div');
                tableContainer.innerHTML = `<div class="recording-table"><div class="recording-table-header"><div class="recording-cell cell-time">Начало</div><div class="recording-cell cell-duration">Длит.</div><div class="recording-cell cell-title">Наименование</div><div class="recording-cell cell-files">Файлы</div></div><div class="recording-table-body"></div></div>`;
                groupEl.appendChild(tableContainer); // Append table to the date group
                weekGroupEl.appendChild(groupEl); // Append the date group to the correct week group

                if (expandedGroups.has(groupData.date)) {
                    const groupEl = weekGroupEl.querySelector(`.date-group[data-date="${groupData.date}"]`);
                    if (groupEl) await loadRecordingsForGroup(groupEl, groupData.date);
                }
            }
        }
    } catch (error) {
        console.error('Error updating recordings list:', error);
    }
}

async function checkForRecordingUpdates() {
    if (isUpdatesPaused) return;
    try {
        const response = await fetch('/recordings_state');
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
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

async function handleAction(taskType, { date, filename }) {
    const settings = await (await fetch('/get_web_settings')).json();

    const performAction = async (settingsFromModal = null) => {
        const endpoint = settingsFromModal
            ? `/update_metadata_and_recreate/${taskType}/${date}/${filename}`
            : `/recreate_${taskType}/${date}/${filename}`;

        await fetch(endpoint, {
            method: 'POST',
            headers: settingsFromModal ? { 'Content-Type': 'application/json' } : {},
            body: settingsFromModal ? JSON.stringify(settingsFromModal) : null
        });
    };

    if (settings.confirm_prompt_on_action) {
        // Показываем большое модальное окно для подтверждения и изменения настроек
        showConfirmationModal(performAction, { date, filename });
    } else {
        performAction();
    }
}

function handleRecordingsListClick(e) {
    const target = e.target;

    if (target.classList.contains('editable-title')) {
        const { date, filename, promptAddition } = target.dataset;
        const currentTitle = target.textContent;
        const row = target.closest('.recording-table-row');

        // Показываем кнопки пересоздания
        row.classList.add('is-editing');

        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentTitle;
        input.className = 'title-edit-input input-field';

        target.replaceWith(input);
        input.focus();
        input.select();

        let promptRow = null;
        if (promptAddition) {
            promptRow = document.createElement('div');
            promptRow.className = 'prompt-display-row';
            const promptContent = document.createElement('div');
            promptContent.className = 'prompt-addition-display';
            promptContent.innerHTML = `<pre>${escapeHtml(promptAddition)}</pre>`;
            promptRow.appendChild(promptContent);
            row.parentNode.insertBefore(promptRow, row.nextSibling);
        }

        const handleOutsideClick = (event) => {
            const isClickInsideRow = row.contains(event.target);
            const isClickInsidePrompt = promptRow ? promptRow.contains(event.target) : false;

            if (!isClickInsideRow && !isClickInsidePrompt) {
                saveTitle();
                row.classList.remove('is-editing'); // Скрываем кнопки
                document.removeEventListener('mousedown', handleOutsideClick);
            }
        };
        document.addEventListener('mousedown', handleOutsideClick);

        const saveTitle = async () => {
            const newTitle = input.value.trim();
            if (newTitle && newTitle !== currentTitle) {
                target.dataset.promptAddition = promptAddition;
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
            row.classList.remove('is-editing'); // Скрываем кнопки
            document.removeEventListener('mousedown', handleOutsideClick);
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                input.blur();
            } else if (e.key === 'Escape') {
                target.textContent = currentTitle;
                if (promptRow) promptRow.remove();
                document.removeEventListener('mousedown', handleOutsideClick);
                row.classList.remove('is-editing'); // Скрываем кнопки
                input.replaceWith(target);
            }
        });
    }

    if (target.classList.contains('recreate-transcription-btn')) {
        handleAction('transcription', target.dataset);
    } else if (target.classList.contains('recreate-protocol-btn')) {
        handleAction('protocol', target.dataset);
    }

    if (target.classList.contains('delete-recording-btn')) {
        const { date, filename } = target.dataset;
        const row = target.closest('.recording-table-row');
        if (confirm(`Вы уверены, что хотите удалить запись и все связанные с ней файлы (${filename})? Это действие необратимо.`)) {
            fetch(`/delete_recording/${date}/${filename}`, {
                method: 'DELETE',
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ok') {
                    // Проверяем, есть ли сразу после удаляемой строки блок с доп. информацией
                    const nextSibling = row.nextElementSibling;
                    if (nextSibling && nextSibling.classList.contains('prompt-display-row')) {
                        nextSibling.remove();
                    }
                    // Удаляем саму строку записи
                    row.remove();
                } else {
                    alert(`Ошибка при удалении: ${data.message}`);
                }
            })
            .catch(error => alert(`Произошла ошибка: ${error}`));
        }
    }

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

    const weekHeader = e.target.closest('.week-group > h4');
    if (weekHeader) {
        const weekGroupEl = weekHeader.parentElement;
        weekGroupEl.classList.toggle('collapsed');
    }
}

export function initRecordingsList() {
    if (!recordingsListContainer) return;

    updateRecordingsList();
    if (updatesIntervalId) clearInterval(updatesIntervalId);
    updatesIntervalId = setInterval(checkForRecordingUpdates, 5000);

    recordingsListContainer.addEventListener('click', handleRecordingsListClick);
}
