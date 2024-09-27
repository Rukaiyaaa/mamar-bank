from django import forms
from .models import Transaction, UserBankAccount
from django.contrib.auth.models import User
from decimal import Decimal

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            'amount',
            'transaction_type'
        ]

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account') # account value ke pop kore anlam
        super().__init__(*args, **kwargs)
        self.fields['transaction_type'].disabled = True # ei field disable thakbe
        self.fields['transaction_type'].widget = forms.HiddenInput() # user er theke hide kora thakbe

    def save(self, commit=True):
        self.instance.account = self.account
        self.instance.balance_after_transaction = self.account.balance
        return super().save()
    

class DepositForm(TransactionForm):
    def clean_amount(self): # amount field ke filter korbo
        min_deposit_amount = 100
        amount = self.cleaned_data.get('amount') # user er fill up kora form theke amra amount field er value ke niye aslam, 50
        if amount < min_deposit_amount:
            raise forms.ValidationError(
                f'You need to deposit at least {min_deposit_amount} $'
            )

        return amount


class WithdrawForm(TransactionForm):

    def clean_amount(self):
        account = self.account
        min_withdraw_amount = 500
        max_withdraw_amount = 20000
        balance = account.balance # 1000
        amount = self.cleaned_data.get('amount')
        if amount < min_withdraw_amount:
            raise forms.ValidationError(
                f'You can withdraw at least {min_withdraw_amount} $'
            )

        if amount > max_withdraw_amount:
            raise forms.ValidationError(
                f'You can withdraw at most {max_withdraw_amount} $'
            )

        if amount > balance: # amount = 5000, tar balance ache 200
            raise forms.ValidationError(
                f'You have {balance} $ in your account. '
                'You can not withdraw more than your account balance'
            )

        return amount



class LoanRequestForm(TransactionForm):
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')

        return amount
    


class TransferForm(forms.ModelForm):
    recipient_username = forms.CharField(max_length=150, label='Recipient Username')

    class Meta:
        model = Transaction
        fields = [
            'amount',
            'transaction_type'
        ]

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account')  
        super().__init__(*args, **kwargs)
        
        self.fields['transaction_type'].disabled = True
        self.fields['transaction_type'].widget = forms.HiddenInput()
        
        
        self.initial['transaction_type'] = 5  

    def clean_recipient_username(self):
        recipient_username = self.cleaned_data.get('recipient_username')
        
        try:
            recipient_user = User.objects.get(username=recipient_username)
            recipient_account = UserBankAccount.objects.get(user=recipient_user)
        except (User.DoesNotExist, UserBankAccount.DoesNotExist):
            raise forms.ValidationError(f"Account with username '{recipient_username}' not found.")
        
       
        self.recipient_account = recipient_account
        return recipient_username

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        
        if amount <= 0:
            raise forms.ValidationError("Transfer amount must be greater than zero.")
        
        if self.account.balance < amount:
            raise forms.ValidationError(f"Insufficient balance. You have {self.account.balance}.")
        
        return amount

    def save(self, commit=True):
        amount = self.cleaned_data['amount']

        self.instance.account = self.account
        self.instance.recipient_account = self.recipient_account
        self.instance.balance_after_transaction = self.account.balance - amount
        self.instance.transaction_type = 5  

        self.account.balance = self.instance.balance_after_transaction   
        self.recipient_account.balance += amount  
        self.account.save()
        self.recipient_account.save()
        

        return super().save(commit=commit)
