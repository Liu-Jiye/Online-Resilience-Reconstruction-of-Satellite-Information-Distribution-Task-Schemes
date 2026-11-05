"""Search-side interval intersection; final validity is independently checked."""
from .models import Item


def opportunities(instance, task):
    return sorted((max(task.release, c.start), min(task.deadline, c.end) - task.duration)
                  for c in instance.contacts
                  if (c.sender, c.receiver) == (task.sender, task.receiver)
                  and max(task.release, c.start) + task.duration <= min(task.deadline, c.end))


def earliest(instance, task, plan, check_deadline=lambda: None):
    """All free-segment left boundaries, including either endpoint's task ends."""
    occupied = [(p.start, p.end) for p in plan
                if {p.sender, p.receiver} & {task.sender, task.receiver}]
    occupied += [(b.start, b.end) for b in instance.calendar
                 if b.resource in (task.sender, task.receiver)]
    occupied.sort()
    for left, latest in opportunities(instance, task):
        check_deadline()
        start = left
        for a, b in occupied:
            check_deadline()
            if b <= start:
                continue
            if a >= start + task.duration:
                break
            start = b
            if start > latest:
                break
        if start <= latest:
            return Item(task.id, task.sender, task.receiver, start, start + task.duration)
    return None
