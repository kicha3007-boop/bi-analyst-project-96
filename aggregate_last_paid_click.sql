-- Расходы и результаты рекламы по модели атрибуции Last Paid Click.
-- Строка витрины — день визита и метки utm_source / utm_medium / utm_campaign:
-- сколько визитов, лидов и покупок дал последний платный клик в этот день
-- и сколько в этот день потрачено на рекламу с теми же метками.
-- В csv выгружаются первые 15 строк: make reports.
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

last_paid_click as (
    -- Витрина Last Paid Click (как в last_paid_click.sql): последний
    -- платный визит посетителя и лид, созданный во время или после него
    select
        ps.visitor_id,
        ps.visit_date,
        ps.utm_source,
        ps.utm_medium,
        ps.utm_campaign,
        l.lead_id,
        l.amount,
        l.closing_reason,
        l.status_id
    from paid_sessions as ps
    left join leads as l
        on
            ps.visitor_id = l.visitor_id
            and ps.visit_date <= l.created_at
    where ps.visit_rank = 1
),

visits_by_day as (
    -- Визиты, лиды и покупки по дню визита и меткам.
    -- Покупка — успешно закрытый лид: closing_reason = 'Успешно реализовано'
    -- или status_id = 142 (код успешной сделки в CRM)
    select
        visit_date::date as visit_date,
        utm_source,
        utm_medium,
        utm_campaign,
        count(visitor_id) as visitors_count,
        count(lead_id) as leads_count,
        count(lead_id) filter (
            where closing_reason = 'Успешно реализовано' or status_id = 142
        ) as purchases_count,
        sum(amount) filter (
            where closing_reason = 'Успешно реализовано' or status_id = 142
        ) as revenue
    from last_paid_click
    group by
        visit_date::date,
        utm_source,
        utm_medium,
        utm_campaign
),

ads as (
    -- Расходы VK и Яндекса за день с теми же метками, что у визитов
    select
        campaign_date::date as campaign_date,
        utm_source,
        utm_medium,
        utm_campaign,
        daily_spent
    from vk_ads
    union all
    select
        campaign_date::date as campaign_date,
        utm_source,
        utm_medium,
        utm_campaign,
        daily_spent
    from ya_ads
),

costs_by_day as (
    select
        campaign_date,
        utm_source,
        utm_medium,
        utm_campaign,
        sum(daily_spent) as total_cost
    from ads
    group by
        campaign_date,
        utm_source,
        utm_medium,
        utm_campaign
)

select
    v.visit_date,
    v.visitors_count,
    v.utm_source,
    v.utm_medium,
    v.utm_campaign,
    c.total_cost,
    v.leads_count,
    v.purchases_count,
    v.revenue
from visits_by_day as v
left join costs_by_day as c
    on
        v.visit_date = c.campaign_date
        and v.utm_source = c.utm_source
        and v.utm_medium = c.utm_medium
        and v.utm_campaign = c.utm_campaign
order by
    v.revenue desc nulls last,
    v.visit_date asc,
    v.visitors_count desc,
    v.utm_source asc,
    v.utm_medium asc,
    v.utm_campaign asc;
