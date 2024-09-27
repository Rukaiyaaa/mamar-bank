from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.http import HttpResponse
from django.views.generic import CreateView, ListView, FormView
from .models import UserBankAccount
from transactions.constants import DEPOSIT, WITHDRAWAL,LOAN, LOAN_PAID
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings 
from datetime import datetime
from django.db.models import Sum
from transactions.forms import (
    DepositForm,
    WithdrawForm,
    LoanRequestForm,
    TransferForm
)
from transactions.models import Transaction


def send_transaction_email(user, amount, subject, template):
        message = render_to_string(template, {
            'user' : user,
            'amount' : amount,
        })
        send_email = EmailMultiAlternatives(subject, '', to=[user.email])
        send_email.attach_alternative(message, "text/html")
        send_email.send()

class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'account': self.request.user.account
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs) # template e context data pass kora
        context.update({
            'title': self.title
        })

        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        # if not account.initial_deposit_date:
        #     now = timezone.now()
        #     account.initial_deposit_date = now
        account.balance += amount # amount = 200, tar ager balance = 0 taka new balance = 0+200 = 200
        account.save(
            update_fields=[
                'balance'
            ]
        )

        messages.success(
            self.request,
            f'{"{:,.2f}".format(float(amount))}$ was deposited to your account successfully'
        )

        send_transaction_email(self.request.user, amount, "Deposite Message", "transactions/deposit_email.html")

        return super().form_valid(form)
    

class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money'

    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        current_balance = self.request.user.account.balance

        if amount > current_balance:
            # If the amount to withdraw is more than the available balance
            messages.error(
                self.request,
                'Unable to process the transaction. The bank is bankrupt!'
            )
            return self.form_invalid(form)  # Prevent form submission if funds are insufficient

        # Otherwise, proceed with the withdrawal
        self.request.user.account.balance -= amount
        self.request.user.account.save(update_fields=['balance'])

        messages.success(
            self.request,
            f'Successfully withdrawn {"{:,.2f}".format(float(amount))}$ from your account'
        )

        send_transaction_email(self.request.user, amount, "Withdrawal Message", "transactions/withdrawal_email.html")

        return super().form_valid(form)


class LoanRequestView(TransactionCreateMixin):
    form_class = LoanRequestForm
    title = 'Request For Loan'

    def get_initial(self):
        initial = {'transaction_type': LOAN}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        current_loan_count = Transaction.objects.filter(
            account=self.request.user.account,transaction_type=3,loan_approve=True).count()
        if current_loan_count >= 3:
            return HttpResponse("You have cross the loan limits")
        messages.success(
            self.request,
            f'Loan request for {"{:,.2f}".format(float(amount))}$ submitted successfully'
        )

        send_transaction_email(self.request.user, amount, "Loan Request Message", "transactions/loan_email.html")

        return super().form_valid(form)
    
class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    balance = 0 # filter korar pore ba age amar total balance ke show korbe
    
    def get_queryset(self):
        queryset = super().get_queryset().filter(
            account=self.request.user.account
        )
        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            queryset = queryset.filter(timestamp__date__gte=start_date, timestamp__date__lte=end_date)
            self.balance = Transaction.objects.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date
            ).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance
       
        return queryset.distinct() # unique queryset hote hobe
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'account': self.request.user.account
        })

        return context
    
        
class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(Transaction, id=loan_id)
        print(loan)
        if loan.loan_approve:
            user_account = loan.account
                # Reduce the loan amount from the user's balance
                # 5000, 500 + 5000 = 5500
                # balance = 3000, loan = 5000
            if loan.amount < user_account.balance:
                user_account.balance -= loan.amount
                loan.balance_after_transaction = user_account.balance
                user_account.save()
                loan.loan_approved = True
                loan.transaction_type = LOAN_PAID
                loan.save()
                return redirect('transactions:loan_list')
            else:
                messages.error(
            self.request,
            f'Loan amount is greater than available balance'
        )

        return redirect('loan_list')


class LoanListView(LoginRequiredMixin,ListView):
    model = Transaction
    template_name = 'transactions/loan_request.html'
    context_object_name = 'loans' # loan list ta ei loans context er moddhe thakbe
    
    def get_queryset(self):
        user_account = self.request.user.account
        queryset = Transaction.objects.filter(account=user_account,transaction_type=3)
        print(queryset)
        return queryset 


# class TransferMoneyView(TransactionCreateMixin):
#     form_class = TransferForm
#     template_name = 'transactions/transaction_form.html'
#     title = 'Transfer Money'
#     success_url = reverse_lazy('transaction_report')

#     def get_form_kwargs(self):
#         kwargs = super().get_form_kwargs()
#         kwargs['account'] = self.request.user.account  
#         return kwargs

#     def form_valid(self, form):
#         messages.success(self.request, f"Successfully transferred {form.cleaned_data['amount']} to {form.cleaned_data['recipient_username']}.")
#         return super().form_valid(form)

#     def form_invalid(self, form):
#         messages.error(self.request, "Transfer failed. Please check your details.")
#         return super().form_invalid(form)
        


class TransferMoneyView(TransactionCreateMixin):
    form_class = TransferForm
    template_name = 'transactions/transaction_form.html'
    title = 'Transfer Money'
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['account'] = self.request.user.account  
        return kwargs

    def form_valid(self, form):
        
        sender = self.request.user
        receiver_username = form.cleaned_data['recipient_username']
        receiver = User.objects.get(username=receiver_username)
        
        self.send_email_transaction(sender, receiver, form.cleaned_data['amount'])
        
        messages.success(self.request, f"Successfully transferred {form.cleaned_data['amount']} to {receiver_username}.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Transfer failed. Please check your details.")
        return super().form_invalid(form)

    
    def send_email_transaction(self, sender, receiver, amount):
        subject = 'Money Transfer Notification'
        
    
        send_mail(
            subject,
            f'You have successfully transferred {amount}$ to {receiver.username}.',
            settings.EMAIL_HOST_USER,  
            [sender.email],  
            fail_silently=False,
        )
        
       
        send_mail(
            subject,
            f'You have received {amount}$ from {sender.username}.',
            settings.EMAIL_HOST_USER, 
            [receiver.email], 
            fail_silently=False,
        )
