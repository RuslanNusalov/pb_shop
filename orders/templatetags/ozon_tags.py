from django import template

register = template.Library()

@register.filter
def format_working_hours(working_hours):
    """
    Преобразует сырой JSON working_hours от Ozon в читаемый вид.
    Пример: "Ежедневно 9:00-21:00" или "Пн-Пт 9:00-21:00, Сб-Вс 10:00-20:00"
    """
    if not working_hours:
        return "Часы работы не указаны"
    
    try:
        # working_hours - это список дней с периодами
        if isinstance(working_hours, str):
            import json
            working_hours = json.loads(working_hours)
        
        if not isinstance(working_hours, list) or len(working_hours) == 0:
            return "Часы работы не указаны"
        
        # Берём первый день как образец
        first_day = working_hours[0]
        periods = first_day.get('periods', [])
        
        if not periods:
            return "Выходной"
        
        # Берём первый период дня
        period = periods[0]
        min_time = period.get('min', {})
        max_time = period.get('max', {})
        
        open_hour = min_time.get('hours', 0)
        open_min = min_time.get('minutes', 0)
        close_hour = max_time.get('hours', 0)
        close_min = max_time.get('minutes', 0)
        
        open_str = f"{open_hour:02d}:{open_min:02d}"
        close_str = f"{close_hour:02d}:{close_min:02d}"
        
        # Проверяем, одинаковое ли расписание во все дни
        all_same = True
        for day in working_hours[1:]:
            day_periods = day.get('periods', [])
            if not day_periods:
                all_same = False
                break
            day_period = day_periods[0]
            if (day_period.get('min', {}).get('hours') != open_hour or
                day_period.get('min', {}).get('minutes') != open_min or
                day_period.get('max', {}).get('hours') != close_hour or
                day_period.get('max', {}).get('minutes') != close_min):
                all_same = False
                break
        
        if all_same:
            return f"Ежедневно {open_str}-{close_str}"
        else:
            return f"{open_str}-{close_str} (график varies)"
            
    except Exception as e:
        return "Часы работы не указаны"