-- Запросы дашборда «Онлайн-школа: сквозная аналитика» и расчёты
-- для презентации.
-- Часть 1 создаёт витрины в схеме dashboard — по ним построены датасеты
-- Superset. Часть 2 — запросы, по которым считались выводы презентации.
-- Файл выполняется при первом старте базы (db/init/20_dashboard.sh)
-- и командой make load.

-- ===================== Часть 1. Витрины дашборда =====================

create schema if not exists dashboard;

-- Платными считаются переходы с этими типами рекламных кампаний (шаг 3).
-- Список задан один раз, остальные витрины ссылаются на него.
create or replace view dashboard.paid_mediums as
select pm.medium
from (
    values
    ('cpc'),
    ('cpm'),
    ('cpa'),
    ('youtube'),
    ('cpp'),
    ('tg'),
    ('social')
) as pm (medium);

-- Витрина Last Paid Click (логика last_paid_click.sql): последний платный
-- визит каждого посетителя и лид, созданный во время или после него.
create or replace view dashboard.last_paid_click as
with paid_sessions as (
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
    inner join dashboard.paid_mediums as pm
        on s.medium = pm.medium
)

select
    ps.visitor_id,
    ps.visit_date,
    ps.utm_source,
    ps.utm_medium,
    ps.utm_campaign,
    l.lead_id,
    l.created_at,
    l.amount,
    l.closing_reason,
    l.status_id,
    -- Покупка — успешно закрытый лид (условие из шага 4)
    coalesce(
        l.closing_reason = 'Успешно реализовано' or l.status_id = 142,
        false
    ) as is_purchase
from paid_sessions as ps
left join leads as l
    on
        ps.visitor_id = l.visitor_id
        and ps.visit_date <= l.created_at
where ps.visit_rank = 1;

-- Расходы на рекламу VK и Яндекса по дням и меткам.
create or replace view dashboard.ads_costs as
with ads as (
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
)

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
    utm_campaign;

-- Агрегат Last Paid Click (логика aggregate_last_paid_click.sql): визиты,
-- лиды, покупки и выручка по дню визита и меткам, расходы с теми же
-- метками и датой.
create or replace view dashboard.aggregate_last_paid_click as
with visits_by_day as (
    select
        visit_date::date as visit_date,
        utm_source,
        utm_medium,
        utm_campaign,
        count(visitor_id) as visitors_count,
        count(lead_id) as leads_count,
        count(lead_id) filter (where is_purchase) as purchases_count,
        sum(amount) filter (where is_purchase) as revenue
    from dashboard.last_paid_click
    group by
        visit_date::date,
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
left join dashboard.ads_costs as c
    on
        v.visit_date = c.campaign_date
        and v.utm_source = c.utm_source
        and v.utm_medium = c.utm_medium
        and v.utm_campaign = c.utm_campaign;

-- Все визиты сайта (и платные, и бесплатные) с признаком типа трафика.
create or replace view dashboard.sessions as
select
    s.visitor_id,
    s.visit_date,
    s.landing_page,
    s.source as utm_source,
    s.medium as utm_medium,
    s.campaign as utm_campaign,
    case
        when pm.medium is not null then 'Платный'
        else 'Бесплатный'
    end as traffic_type
from sessions as s
left join dashboard.paid_mediums as pm
    on s.medium = pm.medium;

-- ============== Часть 2. Расчёты для выводов презентации ==============

-- 1. Общие показатели за июнь 2023: посетители, лиды, покупки, выручка
-- (по всей базе и по витрине Last Paid Click) и все расходы на рекламу.
select
    (
        select count(distinct s.visitor_id)
        from dashboard.sessions as s
    ) as visitors,
    (
        select count(distinct s.visitor_id)
        from dashboard.sessions as s
        where s.traffic_type = 'Платный'
    ) as paid_visitors,
    (select count(*) from leads) as all_leads,
    (
        select count(lpc.lead_id)
        from dashboard.last_paid_click as lpc
    ) as attributed_leads,
    (
        select count(lpc.lead_id)
        from dashboard.last_paid_click as lpc
        where lpc.is_purchase
    ) as attributed_purchases,
    (
        select sum(lpc.amount)
        from dashboard.last_paid_click as lpc
        where lpc.is_purchase
    ) as attributed_revenue,
    (select sum(ac.total_cost) from dashboard.ads_costs as ac) as ads_cost;

-- 2. Метрики по utm_source по модели Last Paid Click (как в дашборде).
-- NULLIF защищает от деления на ноль: метрика пустая, строка остаётся.
select
    utm_source,
    sum(visitors_count) as visitors_count,
    sum(leads_count) as leads_count,
    sum(purchases_count) as purchases_count,
    sum(total_cost) as total_cost,
    coalesce(sum(revenue), 0) as revenue,
    round(sum(total_cost)::numeric / nullif(sum(visitors_count), 0), 2) as cpu,
    round(sum(total_cost)::numeric / nullif(sum(leads_count), 0), 2) as cpl,
    round(
        sum(total_cost)::numeric / nullif(sum(purchases_count), 0), 2
    ) as cppu,
    round(
        (coalesce(sum(revenue), 0) - sum(total_cost)) * 100.0
        / nullif(sum(total_cost), 0),
        2
    ) as roi
from dashboard.aggregate_last_paid_click
group by utm_source
order by
    visitors_count desc,
    utm_source asc;

-- 3. Метрики по source / medium / campaign для кампаний с расходами.
select
    utm_source,
    utm_medium,
    utm_campaign,
    sum(visitors_count) as visitors_count,
    sum(leads_count) as leads_count,
    sum(purchases_count) as purchases_count,
    sum(total_cost) as total_cost,
    coalesce(sum(revenue), 0) as revenue,
    round(sum(total_cost)::numeric / nullif(sum(visitors_count), 0), 2) as cpu,
    round(sum(total_cost)::numeric / nullif(sum(leads_count), 0), 2) as cpl,
    round(
        sum(total_cost)::numeric / nullif(sum(purchases_count), 0), 2
    ) as cppu,
    round(
        (coalesce(sum(revenue), 0) - sum(total_cost)) * 100.0
        / nullif(sum(total_cost), 0),
        2
    ) as roi
from dashboard.aggregate_last_paid_click
group by
    utm_source,
    utm_medium,
    utm_campaign
having sum(total_cost) > 0
order by
    roi desc,
    utm_source asc,
    utm_campaign asc;

-- 4. Окупаемость с учётом всех трат рекламного кабинета: выручка
-- по модели Last Paid Click против полной суммы расходов VK и Яндекса.
with revenue_by_source as (
    select
        utm_source,
        sum(revenue) as revenue
    from dashboard.aggregate_last_paid_click
    group by utm_source
),

cost_by_source as (
    select
        utm_source,
        sum(total_cost) as ads_cost
    from dashboard.ads_costs
    group by utm_source
)

select
    c.utm_source,
    c.ads_cost,
    r.revenue,
    round((r.revenue - c.ads_cost) * 100.0 / c.ads_cost, 2) as roi_all_costs
from cost_by_source as c
left join revenue_by_source as r
    on c.utm_source = r.utm_source
order by c.utm_source;

-- 5. Расходы, которым не нашлось визитов с той же датой и метками:
-- в эти дни реклама оплачена, но переходов с такими метками нет.
select
    ac.utm_source,
    min(ac.campaign_date) as first_day,
    max(ac.campaign_date) as last_day,
    count(distinct ac.campaign_date) as cost_days,
    sum(ac.total_cost) as unmatched_cost
from dashboard.ads_costs as ac
left join dashboard.aggregate_last_paid_click as alpc
    on
        ac.campaign_date = alpc.visit_date
        and ac.utm_source = alpc.utm_source
        and ac.utm_medium = alpc.utm_medium
        and ac.utm_campaign = alpc.utm_campaign
where alpc.visit_date is null
group by ac.utm_source
order by unmatched_cost desc;

-- 6. Визиты с метками yandex/cpc и vk/cpc по дням: проверка разметки.
select
    visit_date::date as visit_day,
    count(*) filter (
        where utm_source = 'yandex' and utm_medium = 'cpc'
    ) as yandex_cpc_visits,
    count(*) filter (
        where utm_source = 'vk' and utm_medium = 'cpc'
    ) as vk_cpc_visits
from dashboard.sessions
group by visit_date::date
order by visit_day;

-- 7. За сколько дней после последнего платного клика появляются лиды:
-- медиана и 90-й перцентиль (дни между датой визита и датой лида).
select
    percentile_disc(0.5) within group (
        order by created_at::date - visit_date::date
    ) as median_days,
    percentile_disc(0.9) within group (
        order by created_at::date - visit_date::date
    ) as p90_days
from dashboard.last_paid_click
where lead_id is not null;

-- 8. Связь расходов на рекламу и органики: корреляция по дням.
with daily_cost as (
    select
        campaign_date,
        sum(total_cost) as total_cost
    from dashboard.ads_costs
    group by campaign_date
),

daily_organic as (
    select
        visit_date::date as visit_day,
        count(distinct visitor_id) as organic_visitors
    from dashboard.sessions
    where utm_medium = 'organic'
    group by visit_date::date
)

select
    round(corr(dc.total_cost, dor.organic_visitors)::numeric, 3)
        as cost_organic_corr
from daily_cost as dc
inner join daily_organic as dor
    on dc.campaign_date = dor.visit_day;

-- 9. Органические визиты по дням недели (1 — понедельник).
select
    extract(isodow from visit_date) as day_of_week,
    count(*) as organic_visits
from dashboard.sessions
where utm_medium = 'organic'
group by extract(isodow from visit_date)
order by day_of_week;

-- 10. Лиды, у которых нет платного клика до создания лида.
select count(*) as leads_without_paid_click
from leads as l
where not exists (
    select 1
    from dashboard.last_paid_click as lpc
    where lpc.lead_id = l.lead_id
);

-- 11. Лиды витрины Last Paid Click по дате последнего платного визита:
-- доля лидов, у которых этот визит пришёлся на 1 июня.
select
    count(lead_id) filter (
        where visit_date::date = '2023-06-01'
    ) as leads_june_1,
    count(lead_id) as leads_total,
    round(
        count(lead_id) filter (where visit_date::date = '2023-06-01') * 100.0
        / count(lead_id),
        1
    ) as share_june_1
from dashboard.last_paid_click;

-- 12. Доля платного трафика среди посетителей сайта.
select
    count(distinct visitor_id) filter (where traffic_type = 'Платный')
        as paid_visitors,
    count(distinct visitor_id) as visitors,
    round(
        count(distinct visitor_id) filter (where traffic_type = 'Платный')
        * 100.0 / count(distinct visitor_id),
        1
    ) as paid_share
from dashboard.sessions;
