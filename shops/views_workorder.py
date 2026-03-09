from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _

from .forms import RepairWorkOrderForm
from .models import RepairWorkOrder

@login_required
def work_order_list_create(request):
    user = request.user
    work_orders = RepairWorkOrder.objects.filter(shop__user_accesses__user=user)
    form = RepairWorkOrderForm(user=user)
    if request.method == "POST":
        form = RepairWorkOrderForm(request.POST, user=user)
        if form.is_valid():
            work_order = form.save(commit=False)
            work_order.created_by = user
            work_order.save()
            return redirect("work_order_list_create")
    return render(request, "work_order_list_create.html", {
        "form": form,
        "work_orders": work_orders,
    })
