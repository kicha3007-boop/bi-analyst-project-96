-- Витрина атрибуции лидов по модели Last Paid Click.
-- Каждому посетителю, у которого был хотя бы один платный переход,
-- сопоставляется его последний платный визит, а к визиту — лид,
-- созданный во время или после этого визита.
-- Посетители без лида остаются в витрине с пустыми полями лида.
-- В csv выгружаются первые 10 строк: make reports.
with paid_mediums (medium) as (
    -- Платными считаются переходы с этими типами рекламных кампаний
    values
    ('cpc'),
    ('cpm'),
    ('cpa'),
    ('youtube'),
    ('cpp'),
    ('tg'),
    ('social')
),

paid_sessions as (
    -- Платные визиты с номером от последнего к первому у каждого посетителя
    select
        s.visitor_id,
        s.visit_date,
        s.source as utm_source,
        s.medium as utm_medium,
        s.campaign as utm_campaign,
        row_number() over (
            partition by s.visitor_id
            order by s.visit_date desc
        ) as visit_rank
    from sessions as s
    inner join paid_mediums as pm
        on s.medium = pm.medium
),

last_paid_clicks as (
    -- Модель атрибуции применяется к визитам до присоединения лидов
    select
        visitor_id,
        visit_date,
        utm_source,
        utm_medium,
        utm_campaign
    from paid_sessions
    where visit_rank = 1
)

select
    lpc.visitor_id,
    lpc.visit_date,
    lpc.utm_source,
    lpc.utm_medium,
    lpc.utm_campaign,
    l.lead_id,
    l.created_at,
    l.amount,
    l.closing_reason,
    l.status_id
from last_paid_clicks as lpc
left join leads as l
    on
        lpc.visitor_id = l.visitor_id
        and lpc.visit_date <= l.created_at
order by
    l.amount desc nulls last,
    lpc.visit_date asc,
    lpc.utm_source asc,
    lpc.utm_medium asc,
    lpc.utm_campaign asc;
