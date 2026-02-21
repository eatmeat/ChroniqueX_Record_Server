import {
    contactsListContainer,
    newGroupNameInput,
    addGroupBtn
} from '../dom.js';
import { updatePromptPreview } from './settings.js';

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

function updateSelectedContactsCount() {
    const countElement = document.getElementById('selected-contacts-count');
    if (countElement) {
        const count = selectedContactIds.length;
        countElement.textContent = count > 0 ? `(${count})` : '';
        countElement.style.color = '#3498db';
        countElement.style.fontWeight = 'normal';
    }
}

function updateLocalSelectionState() {
    selectedContactIds = [...document.querySelectorAll('#contacts-list-container .contact-group-list li label input[type="checkbox"]:checked')].map(cb => cb.value).filter(Boolean);
    updateSelectedContactsCount();
}

async function saveSelectionToServer() {
    await fetch('/save_web_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_contacts: selectedContactIds })
    });
}

async function syncChangesToServer() {
    await saveSelectionToServer();
    await updatePromptPreview();
}
const debouncedSyncChanges = debounce(syncChangesToServer, 500);

function updateGroupStates() {
    document.querySelectorAll('.contact-group').forEach(groupEl => {
        const groupNameEl = groupEl.querySelector('.contact-group-name');
        if (!groupNameEl) return;
        const groupName = groupNameEl.textContent;
        const group = contactsData.groups.find(g => g.name === groupName);
        if (!group) return;

        const groupCheckbox = groupEl.querySelector('.contact-group-header input[type="checkbox"]');
        const groupCounterEl = groupEl.querySelector('.group-counter');
        if (!groupCheckbox || !groupCounterEl) return;

        const contactIdsInGroup = group.contacts.map(c => c.id);
        const selectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;
        
        groupCounterEl.textContent = `${selectedCount} / ${contactIdsInGroup.length}`;
        
        groupCheckbox.checked = selectedCount === contactIdsInGroup.length && contactIdsInGroup.length > 0;
        groupCheckbox.indeterminate = selectedCount > 0 && selectedCount < contactIdsInGroup.length;
    });
}

async function deleteContact(id, name) {
    if (!confirm(`Вы уверены, что хотите удалить участника "${name}"?`)) return;
    await fetch(`/contacts/delete/${id}`, { method: 'POST' });
    loadContactsAndSettings();
}

async function deleteGroup(name) {
    if (!confirm(`Вы уверены, что хотите удалить группу "${name}" и всех ее участников?`)) return;
    await fetch(`/groups/delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
    loadContactsAndSettings();
}

function renderContacts() {
    if (!contactsListContainer) return;
    contactsListContainer.innerHTML = '';

    if (!contactsData.groups || contactsData.groups.length === 0) {
        contactsListContainer.insertAdjacentHTML('beforeend', '<p>Список участников пуст. Создайте первую группу.</p>');
        return;
    }

    const sortedGroups = [...contactsData.groups].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    sortedGroups.forEach(group => {
        const groupEl = document.createElement('div');
        groupEl.className = 'contact-group collapsed';

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
        groupNameEl.style.cursor = 'text';
        
        const groupCheckbox = document.createElement('input');
        groupCheckbox.type = 'checkbox';
        groupCheckbox.title = 'Выбрать/снять всех в группе';

        const contactIdsInGroup = group.contacts.map(c => c.id);
        const selectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;
        
        const groupCounterEl = document.createElement('span');
        groupCounterEl.className = 'group-counter';
        groupCounterEl.textContent = `${selectedCount} / ${contactIdsInGroup.length}`;

        groupHeaderEl.appendChild(expandIconWrapper);
        groupHeaderLabel.appendChild(groupCheckbox);
        groupHeaderLabel.appendChild(groupNameEl);
        groupHeaderEl.appendChild(groupHeaderLabel);
        groupHeaderEl.appendChild(groupCounterEl);
        groupEl.appendChild(groupHeaderEl);
        
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
                deleteGroup(oldName);
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
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ old_name: oldName, new_name: newName })
                });

                if (response.ok) {
                    loadContactsAndSettings();
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
            await fetch('/contacts/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, group_name: group.name })
            });
            addInput.value = '';
            loadContactsAndSettings();
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
            checkbox.checked = selectedContactIds.includes(contact.id);
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
                    deleteContact(contact.id, contact.name);
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
                    await fetch(`/contacts/update/${contact.id}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                    });
                    nameSpan.textContent = newName;
                    labelEl.replaceChild(nameSpan, input);
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

        groupEl.appendChild(listEl);
        contactsListContainer.appendChild(groupEl);

        const updateGroupCheckboxState = () => {
            const checkedInGroup = contactIdsInGroup.filter(id => selectedContactIds.includes(id));
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
        groupCounterEl.addEventListener('click', (e) => {
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
    });
    
    contactsListContainer.addEventListener('change', (e) => {
        if (e.target.matches('.contact-group-list input[type="checkbox"]')) {
            updateLocalSelectionState();
            updateGroupStates();
            debouncedSyncChanges();
        }
    });
}

function handleGroupCheckboxChange(isChecked, contactIdsInGroup) {
    const allCheckboxes = document.querySelectorAll('.contact-group-list input[type="checkbox"]');
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
        updateLocalSelectionState();
        updateGroupStates();
        debouncedSyncChanges();
    }
}

async function loadContactsAndSettings() {
    const [contactsRes, settingsRes] = await Promise.all([fetch('/get_contacts'), fetch('/get_web_settings')]);
    contactsData = await contactsRes.json();
    const settings = await settingsRes.json();
    selectedContactIds = settings.selected_contacts || [];
    renderContacts();
    updateSelectedContactsCount();
    updatePromptPreview();
}

export function initContacts() {
    if(!contactsListContainer) return;
    
    setRandomGroupPlaceholder();
    loadContactsAndSettings();
    
    addGroupBtn?.addEventListener('click', async () => {
        const groupName = newGroupNameInput.value.trim();
        if (!groupName) {
            alert('Имя группы не может быть пустым.');
            return;
        }
        await fetch('/contacts/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: `_init_group_`, group_name: groupName })
        });
        newGroupNameInput.value = '';
        loadContactsAndSettings();
    });

    newGroupNameInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addGroupBtn.click();
    });
}
