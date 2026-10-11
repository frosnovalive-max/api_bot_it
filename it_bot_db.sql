-- ================================================================
-- БАЗА ДАННЫХ: Техническая поддержка колледжа (IT-служба)
-- СУБД:      PostgreSQL 15+
-- Схема:     public
-- Ключи:     UUID (gen_random_uuid())
-- Удаление:  soft delete (is_deleted + deleted_at)
-- ================================================================
-- ВНИМАНИЕ: password_hash хранится как MD5.
-- MD5 криптографически небезопасен.
-- Рекомендуется bcrypt / argon2 на уровне приложения.
-- ================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ================================================================
-- 1. СПРАВОЧНИКИ
-- ================================================================

-- 1.1. Роли
CREATE TABLE IF NOT EXISTS roles (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(50) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  roles IS 'Справочник ролей: admin, support, teacher, staff, student';
COMMENT ON COLUMN roles.code IS 'Код роли: admin, support, teacher, staff, student';

-- 1.2. Подразделения (иерархия)
CREATE TABLE IF NOT EXISTS departments (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(255) NOT NULL,
    parent_id  UUID        REFERENCES departments(id),
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE departments IS 'Подразделения учреждения (иерархия через parent_id)';

-- 1.3. Адреса (6 корпусов)
CREATE TABLE IF NOT EXISTS addresses (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255) NOT NULL,
    full_address TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    is_deleted   BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  addresses IS 'Адреса (корпуса) колледжа. Фиксированные: 6 шт.';
COMMENT ON COLUMN addresses.name IS 'Короткое название — улица корпуса';

-- 1.4. Типы обращений
CREATE TABLE IF NOT EXISTS ticket_types (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(50) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ticket_types IS 'Типы: поломка, запрос доступа, заявка на картридж, запрос оборудования';

-- 1.5. Статусы тикетов
CREATE TABLE IF NOT EXISTS ticket_statuses (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code       VARCHAR(50) NOT NULL UNIQUE,
    name       VARCHAR(255) NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ticket_statuses IS 'Статусы: новый, в работе, закрыт, отклонён, отменён, дубль';

-- 1.6. Приоритеты
CREATE TABLE IF NOT EXISTS ticket_priorities (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code       VARCHAR(50) NOT NULL UNIQUE,
    name       VARCHAR(255) NOT NULL,
    weight     SMALLINT    NOT NULL DEFAULT 0,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  ticket_priorities IS 'Приоритеты обращений';
COMMENT ON COLUMN ticket_priorities.weight IS 'Вес для сортировки: больше = выше приоритет';

-- 1.7. Источники обращений
CREATE TABLE IF NOT EXISTS ticket_sources (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code       VARCHAR(50) NOT NULL UNIQUE,
    name       VARCHAR(255) NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ticket_sources IS 'Источники: бот, личное обращение';

-- ================================================================
-- 2. ПОЛЬЗОВАТЕЛИ И СТРУКТУРА
-- ================================================================

-- 2.1. Пользователи (все: сотрудники, педагоги, студенты, иной персонал)
CREATE TABLE IF NOT EXISTS users (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Данные из MAX API (6 полей)
    max_user_id        BIGINT      UNIQUE,
    first_name         VARCHAR(255),
    name               VARCHAR(255),
    username           VARCHAR(255),
    is_bot             BOOLEAN     NOT NULL DEFAULT FALSE,
    last_activity_time BIGINT,

    -- Полный сырой ответ от MAX API
    raw_profile        JSONB,

    -- Привязка к адресу
    default_address_id UUID        REFERENCES addresses(id),

    -- Статус / блокировка
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    is_blocked         BOOLEAN     NOT NULL DEFAULT FALSE,
    block_reason       TEXT,
    blocked_by         UUID        REFERENCES users(id),
    blocked_at         TIMESTAMPTZ,

    -- Рейтинг (геймификация / ограничения)
    rating             INTEGER     NOT NULL DEFAULT 0,

    -- Soft delete
    is_deleted         BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at         TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  users IS 'Все пользователи системы (заявители и сотрудники)';
COMMENT ON COLUMN users.max_user_id IS 'Внешний ID из MAX API (user_id). Может меняться — при смене обновляется';
COMMENT ON COLUMN users.first_name IS 'Имя из MAX API (first_name)';
COMMENT ON COLUMN users.name IS 'Фамилия / отображаемое имя из MAX API (name)';
COMMENT ON COLUMN users.username IS 'Юзернейм из MAX API (username)';
COMMENT ON COLUMN users.is_bot IS 'Признак бота из MAX API (is_bot)';
COMMENT ON COLUMN users.last_activity_time IS 'Unix timestamp (мс) последней активности из MAX API';
COMMENT ON COLUMN users.raw_profile IS 'Полный сырой JSON-ответ профиля от MAX API';
COMMENT ON COLUMN users.default_address_id IS 'Адрес по умолчанию. Подтягивается в тикет, может быть изменён в задаче';
COMMENT ON COLUMN users.rating IS 'Рейтинг пользователя. Отрицательный — основание для ограничений';

CREATE INDEX IF NOT EXISTS idx_users_max_user_id      ON users (max_user_id);
CREATE INDEX IF NOT EXISTS idx_users_username         ON users (username);
CREATE INDEX IF NOT EXISTS idx_users_default_address  ON users (default_address_id);
CREATE INDEX IF NOT EXISTS idx_users_active           ON users (is_active)  WHERE is_active  = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_blocked          ON users (is_blocked) WHERE is_blocked = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_rating           ON users (rating);

-- 2.2. Пользователь ↔ Роль (многие-ко-многим)
CREATE TABLE IF NOT EXISTS user_roles (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id),
    role_id     UUID        NOT NULL REFERENCES roles(id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    UNIQUE (user_id, role_id)
);

COMMENT ON TABLE user_roles IS 'Ассоциативная таблица. Один пользователь — несколько ролей';

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles (user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles (role_id);

-- 2.3. Пользователь ↔ Подразделение
CREATE TABLE IF NOT EXISTS user_departments (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES users(id),
    department_id UUID        NOT NULL REFERENCES departments(id),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, department_id)
);

COMMENT ON TABLE user_departments IS 'Привязка пользователей к подразделениям';

CREATE INDEX IF NOT EXISTS idx_user_dept_user ON user_departments (user_id);
CREATE INDEX IF NOT EXISTS idx_user_dept_dept ON user_departments (department_id);

-- 2.4. Группы исполнителей
CREATE TABLE IF NOT EXISTS executor_groups (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE executor_groups IS 'Группы исполнителей (сетевая, оборудование, 1С и т. д.)';

-- 2.5. Участники групп
CREATE TABLE IF NOT EXISTS executor_group_members (
    id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id  UUID        NOT NULL REFERENCES executor_groups(id),
    user_id   UUID        NOT NULL REFERENCES users(id),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN     NOT NULL DEFAULT TRUE,
    UNIQUE (group_id, user_id)
);

COMMENT ON TABLE executor_group_members IS 'Состав групп исполнителей';

CREATE INDEX IF NOT EXISTS idx_exec_gm_group ON executor_group_members (group_id);
CREATE INDEX IF NOT EXISTS idx_exec_gm_user  ON executor_group_members (user_id);

-- 2.6. Ответственные по адресам (с историей)
CREATE TABLE IF NOT EXISTS address_responsibles (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    address_id UUID        NOT NULL REFERENCES addresses(id),
    user_id    UUID        NOT NULL REFERENCES users(id),
    group_id   UUID        REFERENCES executor_groups(id),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to   TIMESTAMPTZ,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  address_responsibles IS 'Ответственные по адресам. Несколько на адрес. История через valid_from / valid_to';
COMMENT ON COLUMN address_responsibles.valid_to IS 'NULL = запись актуальна';

CREATE INDEX IF NOT EXISTS idx_addr_resp_address ON address_responsibles (address_id);
CREATE INDEX IF NOT EXISTS idx_addr_resp_user    ON address_responsibles (user_id);
CREATE INDEX IF NOT EXISTS idx_addr_resp_group   ON address_responsibles (group_id);
CREATE INDEX IF NOT EXISTS idx_addr_resp_valid   ON address_responsibles (valid_from, valid_to);

-- ================================================================
-- 3. ТИКЕТЫ
-- ================================================================

-- 3.1. Тикеты
CREATE TABLE IF NOT EXISTS tickets (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number BIGINT       GENERATED BY DEFAULT AS IDENTITY UNIQUE,

    type_id       UUID         NOT NULL REFERENCES ticket_types(id),
    status_id     UUID         NOT NULL REFERENCES ticket_statuses(id),
    priority_id   UUID         REFERENCES ticket_priorities(id),
    source_id     UUID         NOT NULL REFERENCES ticket_sources(id),

    title         VARCHAR(500) NOT NULL,
    description   TEXT         NOT NULL,

    author_id     UUID         NOT NULL REFERENCES users(id),
    address_id    UUID         REFERENCES addresses(id),
    cabinet       VARCHAR(100),

    -- Исполнитель (сам себя назначает)
    assigned_to   UUID         REFERENCES users(id),
    assigned_at   TIMESTAMPTZ,

    -- Закрытие (закрывает администратор)
    closed_by     UUID         REFERENCES users(id),
    closed_at     TIMESTAMPTZ,

    -- Дубль
    duplicate_of  UUID         REFERENCES tickets(id),

    -- Оценка качества
    rating         SMALLINT    CHECK (rating >= 1 AND rating <= 5),
    rating_comment TEXT,
    rated_at       TIMESTAMPTZ,

    is_deleted    BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  tickets IS 'Тикеты (обращения) технической поддержки';
COMMENT ON COLUMN tickets.ticket_number IS 'Человекочитаемый номер (автоинкремент)';
COMMENT ON COLUMN tickets.address_id IS 'Адрес задачи. По умолчанию из users.default_address_id, можно изменить';
COMMENT ON COLUMN tickets.cabinet IS 'Кабинет / аудитория. Необязательный';
COMMENT ON COLUMN tickets.assigned_to IS 'Исполнитель. Назначает сам себя, взяв задачу';
COMMENT ON COLUMN tickets.closed_by IS 'Кто закрыл. Закрывает администратор';
COMMENT ON COLUMN tickets.duplicate_of IS 'Ссылка на оригинал (статус «дубль»)';
COMMENT ON COLUMN tickets.rating IS 'Оценка качества решения: 1–5';

CREATE INDEX IF NOT EXISTS idx_tickets_number    ON tickets (ticket_number);
CREATE INDEX IF NOT EXISTS idx_tickets_type      ON tickets (type_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status    ON tickets (status_id);
CREATE INDEX IF NOT EXISTS idx_tickets_priority  ON tickets (priority_id);
CREATE INDEX IF NOT EXISTS idx_tickets_source    ON tickets (source_id);
CREATE INDEX IF NOT EXISTS idx_tickets_author    ON tickets (author_id);
CREATE INDEX IF NOT EXISTS idx_tickets_address   ON tickets (address_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned  ON tickets (assigned_to);
CREATE INDEX IF NOT EXISTS idx_tickets_closed_by ON tickets (closed_by);
CREATE INDEX IF NOT EXISTS idx_tickets_duplicate ON tickets (duplicate_of) WHERE duplicate_of IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tickets_created   ON tickets (created_at DESC);

-- 3.2. Переписка по тикету
CREATE TABLE IF NOT EXISTS ticket_messages (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   UUID        NOT NULL REFERENCES tickets(id),
    author_id   UUID        NOT NULL REFERENCES users(id),
    message     TEXT        NOT NULL,
    is_internal BOOLEAN     NOT NULL DEFAULT FALSE,
    is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  ticket_messages IS 'Переписка по тикету (веб-форма)';
COMMENT ON COLUMN ticket_messages.is_internal IS 'Внутреннее сообщение — видно только сотрудникам';

CREATE INDEX IF NOT EXISTS idx_ticket_msg_ticket ON ticket_messages (ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_msg_author ON ticket_messages (author_id);

-- 3.3. Вложения (метаданные, файлы — в файловом хранилище)
CREATE TABLE IF NOT EXISTS ticket_attachments (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   UUID         NOT NULL REFERENCES tickets(id),
    message_id  UUID         REFERENCES ticket_messages(id),
    file_name   VARCHAR(500) NOT NULL,
    file_type   VARCHAR(255),
    file_size   BIGINT,
    file_path   VARCHAR(1000) NOT NULL,
    uploaded_by UUID         NOT NULL REFERENCES users(id),
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  ticket_attachments IS 'Вложения. Файлы в файловом хранилище, здесь — метаданные';
COMMENT ON COLUMN ticket_attachments.file_path IS 'Путь / URL файла в хранилище';

CREATE INDEX IF NOT EXISTS idx_ticket_att_ticket  ON ticket_attachments (ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_att_message ON ticket_attachments (message_id);

-- 3.4. История изменений тикета
CREATE TABLE IF NOT EXISTS ticket_history (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id  UUID         NOT NULL REFERENCES tickets(id),
    changed_by UUID         NOT NULL REFERENCES users(id),
    field_name VARCHAR(100) NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ticket_history IS 'История изменений: статус, приоритет, адрес, назначение и т. д.';

CREATE INDEX IF NOT EXISTS idx_ticket_hist_ticket  ON ticket_history (ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_hist_changed ON ticket_history (changed_by);
CREATE INDEX IF NOT EXISTS idx_ticket_hist_field   ON ticket_history (field_name);
CREATE INDEX IF NOT EXISTS idx_ticket_hist_created ON ticket_history (created_at DESC);

-- ================================================================
-- 4. ГЕЙМИФИКАЦИЯ
-- ================================================================

-- 4.1. Правила начисления / списания баллов
CREATE TABLE IF NOT EXISTS point_rules (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    code                VARCHAR(100) NOT NULL UNIQUE,
    name                VARCHAR(255) NOT NULL,
    amount              INTEGER      NOT NULL,
    role_id             UUID         REFERENCES roles(id),
    reset_interval_days INTEGER,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  point_rules IS 'Правила начисления / списания баллов';
COMMENT ON COLUMN point_rules.amount IS '> 0 начисление, < 0 списание';
COMMENT ON COLUMN point_rules.role_id IS 'Привязка к роли. NULL = для всех';
COMMENT ON COLUMN point_rules.reset_interval_days IS 'Период обновления баллов (дней). NULL = без обновления';

-- 4.2. Баланс баллов
CREATE TABLE IF NOT EXISTS user_points (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL UNIQUE REFERENCES users(id),
    balance       INTEGER     NOT NULL DEFAULT 0,
    last_reset_at TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  user_points IS 'Текущий баланс баллов пользователя';
COMMENT ON COLUMN user_points.balance IS 'Может быть отрицательным при штрафах';
COMMENT ON COLUMN user_points.last_reset_at IS 'Дата последнего обновления / сброса';

-- 4.3. История транзакций баллов
CREATE TABLE IF NOT EXISTS point_transactions (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL REFERENCES users(id),
    rule_id      UUID         REFERENCES point_rules(id),
    ticket_id    UUID         REFERENCES tickets(id),
    amount       INTEGER      NOT NULL,
    reason       VARCHAR(500) NOT NULL,
    performed_by UUID         NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  point_transactions IS 'История всех начислений и списаний';
COMMENT ON COLUMN point_transactions.amount IS '> 0 начисление (возврат балла), < 0 списание';
COMMENT ON COLUMN point_transactions.performed_by IS 'Кто выполнил операцию (система / сотрудник)';

CREATE INDEX IF NOT EXISTS idx_point_tx_user   ON point_transactions (user_id);
CREATE INDEX IF NOT EXISTS idx_point_tx_ticket ON point_transactions (ticket_id);
CREATE INDEX IF NOT EXISTS idx_point_tx_rule   ON point_transactions (rule_id);
CREATE INDEX IF NOT EXISTS idx_point_tx_created ON point_transactions (created_at DESC);

-- 4.4. Штрафы
CREATE TABLE IF NOT EXISTS penalties (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL REFERENCES users(id),
    ticket_id  UUID         REFERENCES tickets(id),
    reason     VARCHAR(500) NOT NULL,
    amount     INTEGER      NOT NULL,
    issued_by  UUID         NOT NULL REFERENCES users(id),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  penalties IS 'Штрафы (дубли, спам и т. д.)';
COMMENT ON COLUMN penalties.amount IS 'Размер штрафа (отрицательное значение)';

CREATE INDEX IF NOT EXISTS idx_penalties_user   ON penalties (user_id);
CREATE INDEX IF NOT EXISTS idx_penalties_ticket ON penalties (ticket_id);

-- 4.5. Лимиты по ролям
CREATE TABLE IF NOT EXISTS role_limits (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id              UUID    NOT NULL UNIQUE REFERENCES roles(id),
    max_tickets_per_hour INTEGER,
    max_tickets_per_day  INTEGER,
    min_rating           INTEGER,
    require_moderation   BOOLEAN NOT NULL DEFAULT FALSE,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  role_limits IS 'Ограничения на создание тикетов по ролям';
COMMENT ON COLUMN role_limits.min_rating IS 'Минимальный рейтинг. Ниже — блокировка создания';
COMMENT ON COLUMN role_limits.require_moderation IS 'Требуется ли проверка модератором перед созданием';

-- ================================================================
-- 5. МОДЕРАЦИЯ
-- ================================================================

-- 5.1. Чёрный список
CREATE TABLE IF NOT EXISTS blacklist (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id),
    reason     TEXT        NOT NULL,
    blocked_by UUID        NOT NULL REFERENCES users(id),
    blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE  blacklist IS 'Чёрный список пользователей';
COMMENT ON COLUMN blacklist.expires_at IS 'NULL = бессрочная блокировка';

CREATE INDEX IF NOT EXISTS idx_blacklist_user ON blacklist (user_id) WHERE is_active = TRUE;

-- 5.2. Жалобы сотрудников на пользователей
CREATE TABLE IF NOT EXISTS complaints (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    complainant_id   UUID        NOT NULL REFERENCES users(id),
    target_user_id   UUID        NOT NULL REFERENCES users(id),
    ticket_id        UUID        REFERENCES tickets(id),
    reason           TEXT        NOT NULL,
    status           VARCHAR(50) NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','reviewed','resolved','dismissed')),
    reviewed_by      UUID        REFERENCES users(id),
    reviewed_at      TIMESTAMPTZ,
    resolution_note  TEXT,
    is_deleted       BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE complaints IS 'Жалобы сотрудников на пользователей (спам, некорректные обращения)';

CREATE INDEX IF NOT EXISTS idx_complaints_target ON complaints (target_user_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints (status);

-- ================================================================
-- 6. ВЕБ-ПАНЕЛЬ
-- ================================================================

-- 6.1. Аккаунты веб-панели
CREATE TABLE IF NOT EXISTS web_accounts (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL UNIQUE REFERENCES users(id),
    login         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    is_deleted    BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  web_accounts IS 'Аккаунты веб-панели (логин / пароль)';
COMMENT ON COLUMN web_accounts.password_hash IS 'MD5-хэш. ВНИМАНИЕ: MD5 небезопасен! Рекомендуется bcrypt / argon2';

-- 6.2. Аудит действий сотрудников
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         REFERENCES users(id),
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id   UUID,
    old_values  JSONB,
    new_values  JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  audit_log IS 'Аудит действий в веб-панели';
COMMENT ON COLUMN audit_log.action IS 'login, view, create, update, delete, assign, close и т. д.';
COMMENT ON COLUMN audit_log.entity_type IS 'ticket, user, address, role и т. д.';

CREATE INDEX IF NOT EXISTS idx_audit_user    ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity  ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_action  ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC);

-- ================================================================
-- 7. УВЕДОМЛЕНИЯ
-- ================================================================

-- 7.1. Шаблоны
CREATE TABLE IF NOT EXISTS notification_templates (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    code       VARCHAR(100) NOT NULL UNIQUE,
    name       VARCHAR(255) NOT NULL,
    subject    VARCHAR(500),
    body       TEXT         NOT NULL,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE notification_templates IS 'Шаблоны: заявка получена, назначена, решена, просрочена и т. д.';

-- 7.2. Уведомления
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id),
    template_id UUID        REFERENCES notification_templates(id),
    ticket_id   UUID        REFERENCES tickets(id),
    message     TEXT        NOT NULL,
    is_read     BOOLEAN     NOT NULL DEFAULT FALSE,
    is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE notifications IS 'Уведомления пользователям и сотрудникам';

CREATE INDEX IF NOT EXISTS idx_notif_user   ON notifications (user_id);
CREATE INDEX IF NOT EXISTS idx_notif_ticket ON notifications (ticket_id);
CREATE INDEX IF NOT EXISTS idx_notif_unread ON notifications (user_id) WHERE is_read = FALSE;

-- 7.3. История отправки
CREATE TABLE IF NOT EXISTS notification_history (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id UUID        NOT NULL REFERENCES notifications(id),
    status          VARCHAR(50) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','sent','failed')),
    error_message   TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE notification_history IS 'История отправки уведомлений (для разбора проблем)';

CREATE INDEX IF NOT EXISTS idx_notif_hist_notif  ON notification_history (notification_id);
CREATE INDEX IF NOT EXISTS idx_notif_hist_status ON notification_history (status);