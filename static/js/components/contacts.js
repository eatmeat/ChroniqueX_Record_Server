import {
    contactsListContainer,
    contactsContentWrapper,
    newGroupNameInput,
    addGroupBtn,
    modal
} from '../dom.js';
import { getSettingsFromDOM } from '../utils/helpers.js';
import { updatePromptPreview, getSettings } from './settings.js';

let contactsData = {};
let selectedContactIds = [];

const debounce = (fn, delay) => {
    let timeoutId;
    return (...args) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
};

function setRandomGroupPlaceholder() {
    if (!newGroupNameInput) return;
    const adjectives = [ 'Лысый', 'Грустный', 'Танцующий', 'Летающий', 'Пьяный', 'Голодный', 'Задумчивый', 'Испуганный', 'Счастливый', 'Прыгающий', 'Влюблённый', 'Уставший', 'Безумный', 'Сердитый', 'Летающий задом наперёд', 'Танцующий ламбаду' ];
    const nouns = [ 'Хомяк', 'Пингвин', 'Картофель', 'Утюг', 'Кактус', 'Огурец', 'Носок', 'Тапок', 'Холодильник', 'Чайник', 'Ботинок', 'Банан', 'Пульт', 'Коврик', 'Батон', 'Веник', 'Ёршик', 'Тазик', 'Кабачок', 'Бублик', 'Робот', 'Ананас', 'Ниндзя', 'Монитор', 'Принтер' ];
    const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];
    newGroupNameInput.placeholder = `Новая группа: ${getRandomItem(adjectives)} ${getRandomItem(nouns)}`;
}

function generateRandomPlaceholder() {
    const names = ['Иван', 'Борис', 'Анна', 'Семён', 'Максим', 'Людмила', 'Геннадий', 'Ольга', 'Виктор', 'Наталья', 'Пётр', 'Зинаида', 'Руслан', 'Эльвира', 'Дмитрий', 'Клавдия', 'Аркадий', 'Татьяна', 'Юрий', 'Фёдор'];
    const patronymics = ['Вилкович', 'Борисович', 'Ананасович', 'Семёнович', 'Максимович', 'Люциферович', 'Генераторович', 'Огурцовович', 'Викторович', 'Носкович', 'Петрович', 'Закусонович', 'Рулетович', 'Эскимосович', 'Дмитриевич', 'Котлетович', 'Арбузович', 'Тапочкович', 'Юрьевич', 'Фёдорович'];
    const surnames = ['Ложкин', 'Бублик', 'Ананасов', 'Семечкин', 'Максимум', 'Лепёшкин', 'Глюкозов', 'Окрошка', 'Винегретов', 'Носков', 'Пельмёнов', 'Заливной', 'Рулетов', 'Эскимосов', 'Дырявин', 'Котлетов', 'Арбузов', 'Тапкин', 'Юморов', 'Фантазёров'];
    const positions = ['программист', 'бухгалтер', 'дизайнер', 'менеджер', 'аналитик', 'юрист', 'директор', 'редактор', 'тестировщик', 'администратор', 'инженер', 'маркетолог', 'консультант', 'куратор', 'архитектор', 'экономист', 'продюсер', 'секретарь', 'тренер', 'разработчик'];

    const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];

    const name = getRandomItem(names);
    let finalSurname = getRandomItem(surnames);
    let finalPatronymic = getRandomItem(patronymics);
    if (['Анна', 'Людмила', 'Ольга', 'Наталья', 'Зинаида', 'Эльвира', 'Клавдия', 'Татьяна'].includes(name)) {
        if (finalSurname.endsWith('ов') || finalSurname.endsWith('ин') || finalSurname.endsWith('ев')) finalSurname += 'а';
        if (finalPatronymic.endsWith('ич')) finalPatronymic = finalPatronymic.slice(0, -2) + 'на';
    }
    return `${finalSurname} ${name} ${finalPatronymic} — ${getRandomItem(positions)}`;
}

function updateSelectedContactsCount(container = document) {
    const isModal = container !== document;
    const countElement = container.querySelector(isModal ? '#modal-selected-contacts-count' : '#selected-contacts-count');
    
    if (countElement) {
        const selectedIds = isModal
            ? getSettingsFromDOM(container).selected_contacts
            : selectedContactIds;
        // Используем Set для подсчета только уникальных ID
        const count = new Set(selectedIds).size;
        countElement.textContent = count > 0 ? `(${count})` : '';
        countElement.style.color = isModal ? '' : '#3498db';
        countElement.style.fontWeight = isModal ? '' : 'normal';
    }
}

function updateLocalSelectionState() {
    selectedContactIds = [...document.querySelectorAll('#contacts-list-container .contact-group-list li label input[type="checkbox"]:checked')].map(cb => cb.value).filter(Boolean);
    updateSelectedContactsCount();
}

async function handleFetchResponse(response) {
    if (!response.ok) {
        // Диспетчеризуем глобальное событие об ошибке, чтобы его поймал main.js
        document.dispatchEvent(new CustomEvent('fetch-error', { detail: { status: response.status, statusText: response.statusText } }));
        return null; // Прерываем дальнейшую обработку
    }
    return response; // Возвращаем оригинальный ответ, если все в порядке
}

async function saveSelectionToServer(ids) {
    const currentSettings = await getSettings();
    const settingsToSave = { ...currentSettings, selected_contacts: ids };

    return fetch('/save_web_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(settingsToSave)
    });
}

function updateGroupStates(container = document) {
    const isModal = container !== document;
    container.querySelectorAll('.contact-group').forEach(groupEl => {
        const groupNameEl = groupEl.querySelector('.contact-group-name');
        if (!groupNameEl) return;
        // contactsData - глобальная переменная, она всегда актуальна
        const group = contactsData.groups.find(g => g.name === groupNameEl.textContent);
        if (!group) return;
        const currentSelection = isModal ? getSettingsFromDOM(container).selected_contacts : selectedContactIds;

        const groupCheckbox = groupEl.querySelector('.contact-group-header input[type="checkbox"]');
        const groupCounterEl = groupEl.querySelector('.group-counter');
        if (!groupCheckbox || !groupCounterEl) return;

        const contactIdsInGroup = group.contacts.map(c => c.id);
        const selectedInGroup = container.querySelectorAll(`.contact-group-list li input[type="checkbox"][value]:checked`);
        const selectedCount = contactIdsInGroup.filter(id => currentSelection.includes(id)).length;
        groupCounterEl.textContent = `${selectedCount} / ${contactIdsInGroup.length}`;
        
        groupCheckbox.checked = selectedCount === contactIdsInGroup.length && contactIdsInGroup.length > 0;
        groupCheckbox.indeterminate = selectedCount > 0 && selectedCount < contactIdsInGroup.length;
    });
}

async function deleteContact(id, name, container = document) {
    if (!confirm(`Вы уверены, что хотите удалить участника "${name}"?`)) return;
    const response = await fetch(`/contacts/delete/${id}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (await handleFetchResponse(response)) {
        await loadContactsAndSettings(container); // Перезагружаем данные и перерисовываем список
    }
}

async function deleteGroup(name, container = document) {
    if (!confirm(`Вы уверены, что хотите удалить группу "${name}" и всех ее участников?`)) return;
    const response = await fetch(`/groups/delete`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ name }) });
    if (await handleFetchResponse(response)) {
        await loadContactsAndSettings(container); // Перезагружаем данные и перерисовываем список
    }
}

function renderContacts(forceFullRedraw = false, container = document, overrideSelectedIds = null) {
    const isModal = container !== document;
    const listContainer = container.querySelector(isModal ? '#modal-contacts-content-wrapper #contacts-list-container' : '#contacts-list-container');
    if (!listContainer) return;

    function createGroupHeader(group) {
        const groupHeaderEl = document.createElement('div');
        groupHeaderEl.className = 'contact-group-header';
        
        const groupHeaderLabel = document.createElement('label');
        groupHeaderLabel.className = 'contact-group-header-label';
        
        const expandIconWrapper = document.createElement('div');
        expandIconWrapper.className = 'expand-icon-wrapper';
        const expandIcon = document.createElement('span');
        expandIcon.className = 'expand-icon';
        expandIconWrapper.appendChild(expandIcon);
        
        const groupNameEl = document.createElement('h4');
        groupNameEl.className = 'contact-group-name';
        groupNameEl.textContent = group.name;
        groupNameEl.dataset.groupName = group.name; // Add data attribute for easier lookup
        groupNameEl.style.cursor = 'text';
        
        const groupCheckbox = document.createElement('input');
        groupCheckbox.type = 'checkbox';
        groupCheckbox.title = 'Выбрать/снять всех в группе';

        const contactIdsInGroup = group.contacts.map(c => c.id);
        // Используем переданные ID, если они есть, иначе глобальные
        const currentSelection = overrideSelectedIds ?? (isModal ? getSettingsFromDOM(modal).selected_contacts : selectedContactIds);
        const selectedCount = contactIdsInGroup.filter(id => currentSelection.includes(id)).length;


        const groupCounterEl = document.createElement('span');
        groupCounterEl.className = 'group-counter';
        groupCounterEl.textContent = `${selectedCount} / ${contactIdsInGroup.length}`;

        groupHeaderEl.appendChild(expandIconWrapper);
        groupHeaderLabel.appendChild(groupCheckbox);
        groupHeaderLabel.appendChild(groupNameEl);
        groupHeaderEl.appendChild(groupHeaderLabel);
        groupHeaderEl.appendChild(groupCounterEl);

        return { groupHeaderEl, groupNameEl, groupCounterEl, groupCheckbox, expandIconWrapper };
    }
    function bindGroupNameEditing(group, groupHeaderEl, groupNameEl, groupCounterEl, groupHeaderLabel) {
        groupNameEl.addEventListener('click', (e) => {
            e.stopPropagation();
            const oldName = group.name;
            const input = document.createElement('input');
            input.value = oldName;
            input.className = 'contact-name-edit input-field';

            if (groupHeaderEl.contains(groupCounterEl)) groupHeaderEl.removeChild(groupCounterEl);
            groupHeaderLabel.replaceChild(input, groupNameEl);
            input.focus();
            input.select();

            const deleteGroupBtn = document.createElement('button');
            deleteGroupBtn.textContent = '×';
            deleteGroupBtn.className = 'action-btn delete-btn';
            deleteGroupBtn.onmousedown = (e) => {
                e.preventDefault();
                deleteGroup(oldName, container);
            };
            groupHeaderEl.appendChild(deleteGroupBtn);

            const saveChanges = async () => {
                const newName = input.value.trim();
                groupHeaderEl.removeChild(deleteGroupBtn);
                groupHeaderEl.appendChild(groupCounterEl);

                if (newName === oldName || !newName) {
                    groupHeaderLabel.replaceChild(groupNameEl, input);
                    return;
                }
                const response = await fetch(`/groups/update`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    body: JSON.stringify({ old_name: oldName, new_name: newName })
                });

                const handledResponse = await handleFetchResponse(response);
                if (handledResponse && handledResponse.ok) {
                    await loadContactsAndSettings(container); // Перезагружаем данные и перерисовываем список
                } else {
                    alert(`Ошибка: ${(await response.json()).message}`);
                    groupHeaderLabel.replaceChild(groupNameEl, input);
                }
            };

            input.addEventListener('blur', saveChanges);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') input.blur();
                else if (e.key === 'Escape') {
                    groupHeaderEl.appendChild(groupCounterEl);
                    groupHeaderEl.removeChild(deleteGroupBtn);
                    groupHeaderLabel.replaceChild(groupNameEl, input);
                }
            });
        });
    }
    function createContactList(group) {
         const listEl = document.createElement('ul');
        listEl.className = 'contact-group-list';

        const addItemEl = document.createElement('li');
        addItemEl.className = 'add-item-row';
        const addInput = document.createElement('input');
        addInput.type = 'text';
        addInput.placeholder = `Новый учасник: ${generateRandomPlaceholder()}`;
        addInput.className = 'add-item-input input-field';
        const addBtn = document.createElement('button');
        addBtn.textContent = 'Добавить';
        addBtn.className = 'action-btn';
        addBtn.onclick = async () => {
            const name = addInput.value.trim();
            if (!name) {
                alert('Имя участника не может быть пустым.');
                return;
            }
            const response = await fetch('/contacts/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ name, group_name: group.name })
            });
            if (await handleFetchResponse(response)) {
                addInput.value = '';
                await loadContactsAndSettings(container); // Перезагружаем данные и перерисовываем список
            }
        };
        addInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });
        addItemEl.appendChild(addInput);
        addItemEl.appendChild(addBtn);
        listEl.appendChild(addItemEl);

        const sortedContacts = [...group.contacts].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        sortedContacts.forEach(contact => {
            const itemEl = document.createElement('li');
            const labelEl = document.createElement('label');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = contact.id;
            // Используем переданные ID, если они есть, иначе глобальные
            const currentSelection = overrideSelectedIds ?? (isModal ? getSettingsFromDOM(modal).selected_contacts : selectedContactIds);
            checkbox.checked = currentSelection.includes(contact.id);
            labelEl.appendChild(checkbox);
            
            const nameSpan = document.createElement('span');
            nameSpan.className = 'contact-name';
            nameSpan.textContent = contact.name;
            labelEl.appendChild(nameSpan);
            itemEl.appendChild(labelEl);
            listEl.appendChild(itemEl);

            itemEl.addEventListener('click', (e) => {
                // Игнорируем клики по элементам, у которых есть свои обработчики
                // (имя, поле ввода, кнопки, и сам чекбокс).
                // e.target === checkbox - это для прямого клика по чекбоксу.
                if (e.target.closest('.contact-name') || e.target.closest('.contact-name-edit') || e.target.closest('.item-actions') || e.target.tagName === 'INPUT') {
                    return;
                }
                // Если клик был по "пустому" месту в строке (li) или на label,
                // программно кликаем по чекбоксу, чтобы изменить его состояние.
                e.preventDefault();
                checkbox.click();
            });

            nameSpan.addEventListener('click', () => {
                const currentName = nameSpan.textContent;
                const input = document.createElement('input');
                input.type = 'text';
                input.value = currentName;
                input.className = 'contact-name-edit input-field';

                const buttonsContainer = document.createElement('div');
                buttonsContainer.className = 'item-actions';
                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = '×';
                deleteBtn.className = 'action-btn delete-btn';
                deleteBtn.onmousedown = (e) => {
                    e.preventDefault();
                    deleteContact(contact.id, contact.name, container);
                };
                buttonsContainer.appendChild(deleteBtn);

                labelEl.replaceChild(input, nameSpan);
                itemEl.appendChild(buttonsContainer);
                input.focus();
                input.select();

                const saveChanges = async () => {
                    const newName = input.value.trim();
                    itemEl.removeChild(buttonsContainer);
                    if (newName === currentName || !newName) {
                        labelEl.replaceChild(nameSpan, input);
                        return;
                    }
                    const response = await fetch(`/contacts/update/${contact.id}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        body: JSON.stringify({ name: newName })
                    });
                    if (await handleFetchResponse(response)) {
                        nameSpan.textContent = newName;
                        labelEl.replaceChild(nameSpan, input);
                        await loadContactsAndSettings(container);
                    }
                };
                input.addEventListener('blur', saveChanges);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') input.blur();
                    else if (e.key === 'Escape') {
                        itemEl.removeChild(buttonsContainer);
                        labelEl.replaceChild(nameSpan, input);
                    }
                });
            });
        });
        return listEl;
    }

    // --- Основная логика рендеринга ---
    // Capture expanded state from the current DOM before clearing/rebuilding
    const expandedGroupNamesToRestore = new Set();
    // Capture for modal or if full redraw on main page
    if (isModal || forceFullRedraw) {
        document.querySelectorAll('.contact-group:not(.collapsed)').forEach(groupEl => {
            const nameEl = groupEl.querySelector('.contact-group-name');
            if (nameEl) expandedGroupNamesToRestore.add(nameEl.textContent);
        });
    }

    if (forceFullRedraw) {
        listContainer.innerHTML = '';
    }

    if (!contactsData.groups || contactsData.groups.length === 0) {
        listContainer.innerHTML = '<p>Список участников пуст. Создайте первую группу.</p>';
        return;
    }

    const sortedGroups = [...contactsData.groups].sort((a, b) => a.name.localeCompare(b.name, 'ru')); // contactsData is global
    const existingGroupNames = new Set([...listContainer.querySelectorAll('.contact-group-name')].map(el => el.textContent));
    const newGroupNames = new Set(sortedGroups.map(g => g.name));

    // Удаляем группы, которых больше нет
    existingGroupNames.forEach(name => {
        // Note: This assumes group names are unique and stable identifiers.
        // If group names can change, a more robust ID-based lookup would be better.
        if (!newGroupNames.has(name)) {
            const groupEl = [...contactsListContainer.querySelectorAll('.contact-group-name')].find(el => el.textContent === name)?.closest('.contact-group');
            groupEl?.remove();
        }
    });

    sortedGroups.forEach(group => {
        let groupEl = [...listContainer.querySelectorAll('.contact-group-name')].find(el => el.textContent === group.name)?.closest('.contact-group');

        if (groupEl) {
            // Если группа уже существует, обновляем только список контактов внутри нее.
            // Обработчики на заголовке и иконках остаются нетронутыми.
            const listEl = createContactList(group, overrideSelectedIds); // Создаем новый список контактов
            const isCollapsed = groupEl.classList.contains('collapsed');
            
            // Заменяем старый список новым
            groupEl.querySelector('.contact-group-list')?.remove();
            groupEl.appendChild(listEl);
            
            // Восстанавливаем состояние "свернутости", если оно было
            if (isCollapsed) listEl.style.display = 'none';

        } else { // Иначе создаем новую
            groupEl = document.createElement('div');
            groupEl.className = 'contact-group';
            // Set initial collapsed state based on what was captured
            if (expandedGroupNamesToRestore.has(group.name)) {
                groupEl.classList.remove('collapsed');
            } else {
                groupEl.classList.add('collapsed');
            }

            const { groupHeaderEl, groupNameEl, groupCounterEl, groupCheckbox, expandIconWrapper } = createGroupHeader(group);
            groupEl.appendChild(groupHeaderEl);
            bindGroupNameEditing(group, groupHeaderEl, groupNameEl, groupCounterEl, groupHeaderEl.querySelector('.contact-group-header-label'));

            const listEl = createContactList(group, overrideSelectedIds);
            groupEl.appendChild(listEl);
            listContainer.appendChild(groupEl);

            // Привязываем события к новой группе, передавая listEl
            bindGroupEvents(groupEl, groupHeaderEl, groupCheckbox, expandIconWrapper, groupCounterEl, group.contacts.map(c => c.id), listEl);
        }
    });

    function bindGroupEvents(groupEl, groupHeaderEl, groupCheckbox, expandIconWrapper, groupCounterEl, contactIdsInGroup, listEl) {
        const updateGroupCheckboxState = () => {
            const currentSelection = overrideSelectedIds ?? (isModal ? getSettingsFromDOM(modal).selected_contacts : selectedContactIds);
            const checkedInGroup = contactIdsInGroup.filter(id => currentSelection.includes(id));
            groupCheckbox.checked = checkedInGroup.length === contactIdsInGroup.length && contactIdsInGroup.length > 0;
            groupCheckbox.indeterminate = checkedInGroup.length > 0 && checkedInGroup.length < contactIdsInGroup.length;
        };
        updateGroupCheckboxState();
        
        groupCheckbox.addEventListener('change', () => {
            handleGroupCheckboxChange(groupCheckbox.checked, contactIdsInGroup);
        });

        expandIconWrapper.addEventListener('click', (e) => {
            e.stopPropagation();
            groupEl.classList.toggle('collapsed');
        });
         groupHeaderEl.addEventListener('click', (e) => {
            // Определяем, был ли клик по элементу, у которого есть своя функция
            const isSpecificElementClick = e.target.closest('.expand-icon-wrapper') ||
                                           e.target.closest('.contact-group-name') ||
                                           e.target.classList.contains('contact-name-edit') ||
                                           e.target.closest('.group-counter') ||
                                           e.target.classList.contains('contact-group-header-label');

            if (isSpecificElementClick) {
                return;
            }
            const shouldBeChecked = groupCheckbox.indeterminate || !groupCheckbox.checked;
            handleGroupCheckboxChange(shouldBeChecked, contactIdsInGroup);
        });
        groupCounterEl.addEventListener('click', (e) => {
            e.stopPropagation();
            groupEl.classList.toggle('collapsed');
        });
    }
}

function handleGroupCheckboxChange(isChecked, contactIdsInGroup, container = document) {
    const allCheckboxes = container.querySelectorAll('.contact-group-list input[type="checkbox"]');
    let selectionChanged = false;
    allCheckboxes.forEach(cb => {
        if (contactIdsInGroup.includes(cb.value)) {
            if (cb.checked !== isChecked) {
                cb.checked = isChecked;
                selectionChanged = true;
            }
        }
    });

    if (selectionChanged) {
        if (container !== document) { // Если это модальное окно
            // Просто вызываем обновление, которое уже определено в modal.js
            container.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            updateLocalSelectionState();
            updateGroupStates();
            saveSelectionToServer(selectedContactIds).then(() => updatePromptPreview(document));
        }
    }
}

async function loadContactsAndSettings(container = document) {
    const isModal = container !== document;

    const [contactsRes, settingsRes] = await Promise.all([
        fetch('/get_contacts', { headers: { 'X-Requested-With': 'XMLHttpRequest' } }),
        fetch('/get_web_settings', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
    ]);

    if (!await handleFetchResponse(contactsRes) || !await handleFetchResponse(settingsRes)) return;

    contactsData = await contactsRes.json();
    const settings = await settingsRes.json();

    if (isModal) {
        // В модальном окне мы не меняем глобальные selectedContactIds,
        // а просто перерисовываем его содержимое с новыми данными о контактах.
        // Выбранные контакты возьмутся из DOM самого модального окна.
        renderContacts(true, container);
    } else {
        selectedContactIds = settings.selected_contacts || [];
        if (contactsContentWrapper) renderContacts(true, document); // Принудительная полная перерисовка
        updateSelectedContactsCount();
        updatePromptPreview(document);
    }
}

function bindContainerEvents(container, isModal, listContainer, onUpdate, initialSettings) {
    if (!isModal) { // Основная страница
        setRandomGroupPlaceholder();
        loadContactsAndSettings(document);
    } else if (initialSettings) { // Модальное окно с настройками из метаданных
        // Передаем ID выбранных контактов из метаданных напрямую в renderContacts, не трогая глобальную переменную
        renderContacts(true, container, initialSettings.selected_contacts || []);
        updateGroupStates(container);
    } else {
        // Для модального окна (остановка записи) используем текущие глобальные настройки
        renderContacts(true, container, selectedContactIds);
        updateGroupStates(container);
    }

    // --- Обработчики добавления группы ---
    container.querySelector(isModal ? '#modal-contacts-content-wrapper #add-group-btn' : '#add-group-btn')?.addEventListener('click', async () => {
         const groupNameInput = container.querySelector(isModal ? '#modal-contacts-content-wrapper #new-group-name' : '#new-group-name');
         const groupName = groupNameInput.value.trim();
         console.log(`[Contacts] Попытка добавить группу с именем: "${groupName}"`);
         if (!groupName) {
             alert('Имя группы не может быть пустым.');
             return;
         }
         let response = await fetch('/groups/add', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
             body: JSON.stringify({ group_name: groupName })
         });
         response = await handleFetchResponse(response);
         if (response && response.ok) {
             console.log('[Contacts] Группа успешно добавлена на сервере. Обновляем список.');
             groupNameInput.value = '';
             if (!isModal) setRandomGroupPlaceholder();
             await loadContactsAndSettings(container); // Перезагружаем данные и перерисовываем список
         } else {
             const error = await response.json();
             console.error(`[Contacts] Ошибка при добавлении группы: ${error.message}`);
             alert(`Ошибка: ${error.message}`);
         }
    });

    container.querySelector(isModal ? '#modal-contacts-content-wrapper #new-group-name' : '#new-group-name')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') container.querySelector(isModal ? '#modal-contacts-content-wrapper #add-group-btn' : '#add-group-btn').click();
    });

    // --- Единый обработчик на контейнер для всех чекбоксов ---
    // Удаляем предыдущий обработчик, если он был, чтобы избежать дублирования
    const handlerKey = isModal ? '_modalHandler' : '_mainHandler';
    if (listContainer[handlerKey]) {
        listContainer.removeEventListener('change', listContainer[handlerKey]);
    }
    // Создаем и сохраняем новый обработчик
    listContainer[handlerKey] = (e) => {
        if (e.target.matches('.contact-group-list input[type="checkbox"]') || e.target.matches('.contact-group-header input[type="checkbox"]')) {
            if (!isModal) {
                updateLocalSelectionState();
            }
            updateGroupStates(container);
            if (!isModal) {
                const updateCallback = onUpdate || (() => saveSelectionToServer(selectedContactIds).then(() => updatePromptPreview(document)));
                updateCallback();
            }
        }
    };
    listContainer.addEventListener('change', listContainer[handlerKey]);
}

export function initContacts(container = document, onUpdate = null, initialSettings = null) {
    const isModal = container !== document;
    const listContainer = container.querySelector(isModal ? '#modal-contacts-content-wrapper #contacts-list-container' : '#contacts-list-container');
    if(!listContainer) return;

    if (!isModal) {
        // Принудительно перепривязываем события для основной страницы,
        // т.к. они могли быть удалены при открытии модального окна.
        listContainer._mainHandler = null;
    }
    bindContainerEvents(container, isModal, listContainer, onUpdate, initialSettings);
}
export { generateRandomPlaceholder, loadContactsAndSettings, updateSelectedContactsCount };