# -*- coding: utf-8 -*-
"""
kpi.py module containing :class:`~cheshire-cat.kpi.py.<ClassName>` class.
"""
import yfinance as yf
import yahooquery as yq
from pandas import DataFrame, Series
import pandas as pd
from utils import camel_to_snake
from numpy import NaN

class Kpis():
    def __init__(self, ticker, df: DataFrame, info):
        index = df.index
        self.period_type = Series(data=[NaN for _ in index], index=index)
        self.currency_code = Series(data=[NaN for _ in index], index=index)
        self.accounts_payable = Series(data=[NaN for _ in index], index=index)
        self.accounts_receivable = Series(data=[NaN for _ in index], index=index)
        self.accumulated_depreciation = Series(data=[NaN for _ in index], index=index)
        self.available_for_sale_securities = Series(data=[NaN for _ in index], index=index)
        self.basic_average_shares = Series(data=[NaN for _ in index], index=index)
        self.basic_eps = Series(data=[NaN for _ in index], index=index)
        self.beginning_cash_position = Series(data=[NaN for _ in index], index=index)
        self.capital_expenditure = Series(data=[NaN for _ in index], index=index)
        self.capital_stock = Series(data=[NaN for _ in index], index=index)
        self.cash_and_cash_equivalents = Series(data=[NaN for _ in index], index=index)
        self.cash_cash_equivalents_and_short_term_investments = Series(data=[NaN for _ in index], index=index)
        self.cash_dividends_paid = Series(data=[NaN for _ in index], index=index)
        self.cash_equivalents = Series(data=[NaN for _ in index], index=index)
        self.cash_financial = Series(data=[NaN for _ in index], index=index)
        self.cash_flow_from_continuing_financing_activities = Series(data=[NaN for _ in index], index=index)
        self.cash_flow_from_continuing_investing_activities = Series(data=[NaN for _ in index], index=index)
        self.cash_flow_from_continuing_operating_activities = Series(data=[NaN for _ in index], index=index)
        self.change_in_account_payable = Series(data=[NaN for _ in index], index=index)
        self.change_in_cash_supplemental_as_reported = Series(data=[NaN for _ in index], index=index)
        self.change_in_inventory = Series(data=[NaN for _ in index], index=index)
        self.change_in_other_current_assets = Series(data=[NaN for _ in index], index=index)
        self.change_in_other_current_liabilities = Series(data=[NaN for _ in index], index=index)
        self.change_in_other_working_capital = Series(data=[NaN for _ in index], index=index)
        self.change_in_payable = Series(data=[NaN for _ in index], index=index)
        self.change_in_payables_and_accrued_expense = Series(data=[NaN for _ in index], index=index)
        self.change_in_receivables = Series(data=[NaN for _ in index], index=index)
        self.change_in_working_capital = Series(data=[NaN for _ in index], index=index)
        self.changes_in_account_receivables = Series(data=[NaN for _ in index], index=index)
        self.changes_in_cash = Series(data=[NaN for _ in index], index=index)
        self.commercial_paper = Series(data=[NaN for _ in index], index=index)
        self.common_stock = Series(data=[NaN for _ in index], index=index)
        self.common_stock_dividend_paid = Series(data=[NaN for _ in index], index=index)
        self.common_stock_equity = Series(data=[NaN for _ in index], index=index)
        self.common_stock_issuance = Series(data=[NaN for _ in index], index=index)
        self.common_stock_payments = Series(data=[NaN for _ in index], index=index)
        self.cost_of_revenue = Series(data=[NaN for _ in index], index=index)
        self.current_assets = Series(data=[NaN for _ in index], index=index)
        self.current_debt = Series(data=[NaN for _ in index], index=index)
        self.current_debt_and_capital_lease_obligation = Series(data=[NaN for _ in index], index=index)
        self.current_deferred_liabilities = Series(data=[NaN for _ in index], index=index)
        self.current_deferred_revenue = Series(data=[NaN for _ in index], index=index)
        self.current_liabilities = Series(data=[NaN for _ in index], index=index)
        self.deferred_income_tax = Series(data=[NaN for _ in index], index=index)
        self.deferred_tax = Series(data=[NaN for _ in index], index=index)
        self.depreciation_amortization_depletion = Series(data=[NaN for _ in index], index=index)
        self.depreciation_and_amortization = Series(data=[NaN for _ in index], index=index)
        self.diluted_average_shares = Series(data=[NaN for _ in index], index=index)
        self.diluted_eps = Series(data=[NaN for _ in index], index=index)
        self.diluted_ni_availto_com_stockholders = Series(data=[NaN for _ in index], index=index)
        self.ebit = Series(data=[NaN for _ in index], index=index)
        self.end_cash_position = Series(data=[NaN for _ in index], index=index)
        self.financing_cash_flow = Series(data=[NaN for _ in index], index=index)
        self.free_cash_flow = Series(data=[NaN for _ in index], index=index)
        self.gains_losses_not_affecting_retained_earnings = Series(data=[NaN for _ in index], index=index)
        self.gross_ppe = Series(data=[NaN for _ in index], index=index)
        self.gross_profit = Series(data=[NaN for _ in index], index=index)
        self.income_tax_paid_supplemental_data = Series(data=[NaN for _ in index], index=index)
        self.interest_expense = Series(data=[NaN for _ in index], index=index)
        self.interest_expense_non_operating = Series(data=[NaN for _ in index], index=index)
        self.interest_income = Series(data=[NaN for _ in index], index=index)
        self.interest_income_non_operating = Series(data=[NaN for _ in index], index=index)
        self.interest_paid_supplemental_data = Series(data=[NaN for _ in index], index=index)
        self.inventory = Series(data=[NaN for _ in index], index=index)
        self.invested_capital = Series(data=[NaN for _ in index], index=index)
        self.investing_cash_flow = Series(data=[NaN for _ in index], index=index)
        self.investmentin_financial_assets = Series(data=[NaN for _ in index], index=index)
        self.investments_and_advances = Series(data=[NaN for _ in index], index=index)
        self.issuance_of_capital_stock = Series(data=[NaN for _ in index], index=index)
        self.issuance_of_debt = Series(data=[NaN for _ in index], index=index)
        self.land_and_improvements = Series(data=[NaN for _ in index], index=index)
        self.leases = Series(data=[NaN for _ in index], index=index)
        self.long_term_debt = Series(data=[NaN for _ in index], index=index)
        self.long_term_debt_and_capital_lease_obligation = Series(data=[NaN for _ in index], index=index)
        self.long_term_debt_issuance = Series(data=[NaN for _ in index], index=index)
        self.long_term_debt_payments = Series(data=[NaN for _ in index], index=index)
        self.machinery_furniture_equipment = Series(data=[NaN for _ in index], index=index)
        self.net_business_purchase_and_sale = Series(data=[NaN for _ in index], index=index)
        self.net_common_stock_issuance = Series(data=[NaN for _ in index], index=index)
        self.net_debt = Series(data=[NaN for _ in index], index=index)
        self.net_income = Series(data=[NaN for _ in index], index=index)
        self.net_income_common_stockholders = Series(data=[NaN for _ in index], index=index)
        self.net_income_continuous_operations = Series(data=[NaN for _ in index], index=index)
        self.net_income_from_continuing_and_discontinued_operation = Series(data=[NaN for _ in index], index=index)
        self.net_income_from_continuing_operation_net_minority_interest = Series(data=[NaN for _ in index], index=index)
        self.net_income_from_continuing_operations = Series(data=[NaN for _ in index], index=index)
        self.net_income_including_noncontrolling_interests = Series(data=[NaN for _ in index], index=index)
        self.net_interest_income = Series(data=[NaN for _ in index], index=index)
        self.net_investment_purchase_and_sale = Series(data=[NaN for _ in index], index=index)
        self.net_issuance_payments_of_debt = Series(data=[NaN for _ in index], index=index)
        self.net_long_term_debt_issuance = Series(data=[NaN for _ in index], index=index)
        self.net_non_operating_interest_income_expense = Series(data=[NaN for _ in index], index=index)
        self.net_other_financing_charges = Series(data=[NaN for _ in index], index=index)
        self.net_other_investing_changes = Series(data=[NaN for _ in index], index=index)
        self.net_ppe = Series(data=[NaN for _ in index], index=index)
        self.net_ppe_purchase_and_sale = Series(data=[NaN for _ in index], index=index)
        self.net_short_term_debt_issuance = Series(data=[NaN for _ in index], index=index)
        self.net_tangible_assets = Series(data=[NaN for _ in index], index=index)
        self.non_current_deferred_liabilities = Series(data=[NaN for _ in index], index=index)
        self.non_current_deferred_revenue = Series(data=[NaN for _ in index], index=index)
        self.non_current_deferred_taxes_liabilities = Series(data=[NaN for _ in index], index=index)
        self.normalized_ebitda = Series(data=[NaN for _ in index], index=index)
        self.normalized_income = Series(data=[NaN for _ in index], index=index)
        self.operating_cash_flow = Series(data=[NaN for _ in index], index=index)
        self.operating_expense = Series(data=[NaN for _ in index], index=index)
        self.operating_income = Series(data=[NaN for _ in index], index=index)
        self.operating_revenue = Series(data=[NaN for _ in index], index=index)
        self.ordinary_shares_number = Series(data=[NaN for _ in index], index=index)
        self.other_current_assets = Series(data=[NaN for _ in index], index=index)
        self.other_current_borrowings = Series(data=[NaN for _ in index], index=index)
        self.other_current_liabilities = Series(data=[NaN for _ in index], index=index)
        self.other_income_expense = Series(data=[NaN for _ in index], index=index)
        self.other_non_cash_items = Series(data=[NaN for _ in index], index=index)
        self.other_non_current_assets = Series(data=[NaN for _ in index], index=index)
        self.other_non_current_liabilities = Series(data=[NaN for _ in index], index=index)
        self.other_non_operating_income_expenses = Series(data=[NaN for _ in index], index=index)
        self.other_receivables = Series(data=[NaN for _ in index], index=index)
        self.other_short_term_investments = Series(data=[NaN for _ in index], index=index)
        self.payables = Series(data=[NaN for _ in index], index=index)
        self.payables_and_accrued_expenses = Series(data=[NaN for _ in index], index=index)
        self.pretax_income = Series(data=[NaN for _ in index], index=index)
        self.properties = Series(data=[NaN for _ in index], index=index)
        self.purchase_of_business = Series(data=[NaN for _ in index], index=index)
        self.purchase_of_investment = Series(data=[NaN for _ in index], index=index)
        self.purchase_of_ppe = Series(data=[NaN for _ in index], index=index)
        self.receivables = Series(data=[NaN for _ in index], index=index)
        self.reconciled_cost_of_revenue = Series(data=[NaN for _ in index], index=index)
        self.reconciled_depreciation = Series(data=[NaN for _ in index], index=index)
        self.repayment_of_debt = Series(data=[NaN for _ in index], index=index)
        self.repurchase_of_capital_stock = Series(data=[NaN for _ in index], index=index)
        self.research_and_development = Series(data=[NaN for _ in index], index=index)
        self.retained_earnings = Series(data=[NaN for _ in index], index=index)
        self.sale_of_investment = Series(data=[NaN for _ in index], index=index)
        self.selling_general_and_administration = Series(data=[NaN for _ in index], index=index)
        self.share_issued = Series(data=[NaN for _ in index], index=index)
        self.short_term_debt_payments = Series(data=[NaN for _ in index], index=index)
        self.stock_based_compensation = Series(data=[NaN for _ in index], index=index)
        self.stockholders_equity = Series(data=[NaN for _ in index], index=index)
        self.tangible_book_value = Series(data=[NaN for _ in index], index=index)
        self.tax_effect_of_unusual_items = Series(data=[NaN for _ in index], index=index)
        self.tax_provision = Series(data=[NaN for _ in index], index=index)
        self.tax_rate_for_calcs = Series(data=[NaN for _ in index], index=index)
        self.total_assets = Series(data=[NaN for _ in index], index=index)
        self.total_capitalization = Series(data=[NaN for _ in index], index=index)
        self.total_debt = Series(data=[NaN for _ in index], index=index)
        self.total_equity_gross_minority_interest = Series(data=[NaN for _ in index], index=index)
        self.total_expenses = Series(data=[NaN for _ in index], index=index)
        self.total_liabilities_net_minority_interest = Series(data=[NaN for _ in index], index=index)
        self.total_non_current_assets = Series(data=[NaN for _ in index], index=index)
        self.total_non_current_liabilities_net_minority_interest = Series(data=[NaN for _ in index], index=index)
        self.total_operating_income_as_reported = Series(data=[NaN for _ in index], index=index)
        self.total_revenue = Series(data=[NaN for _ in index], index=index)
        self.tradeand_other_payables_non_current = Series(data=[NaN for _ in index], index=index)
        self.working_capital = Series(data=[NaN for _ in index], index=index)

        for c in df.columns:
            self.__dict__[c] = df[c]

        if not self.ebit.all():
            self.ebit = self.operating_income

        self.two_hundred_day_avg_share_price = info["twoHundredDayAverage"]
        self.shares_outstanding = info["sharesOutstanding"]

        self.total_liabilities = self.total_liabilities_net_minority_interest

        self.total_net_liabilities = self.total_liabilities - self.cash_and_cash_equivalents

        self.tax_expense = self.pretax_income - self.net_income

        self.debt_to_equity = self.total_debt / self.stockholders_equity

        self.net_debt_to_equity = self.total_net_liabilities / self.stockholders_equity

        self.quick_ratio = self.current_liabilities / self.stockholders_equity

        self.current_ratio = self.current_assets / self.current_liabilities

        self.intangible_assets = self.total_assets - self.net_tangible_assets

        self.book_value = self.total_assets - self.total_liabilities_net_minority_interest

        self.market_value = self.shares_outstanding * self.two_hundred_day_avg_share_price

        self.price_to_book = self.market_value / self.book_value

        self.cash_to_current_assets = self.cash_and_cash_equivalents / self.current_assets

        self.cash_per_share = self.cash_and_cash_equivalents / self.shares_outstanding

        self.debt_quality_ratio = self.total_debt / self.total_liabilities

        self.debt_ratio = self.total_debt / self.total_assets

        self.debt_service = self.total_debt.diff() + self.interest_expense

    def quick_ratio(self):
        """
        Quick ratio / acid-test ratio

        The acid-test, or quick ratio, compares a company's most short-term assets to
        its most short-term liabilities to see if a company has enough cash to pay
        its immediate liabilities, such as short-term debt. :return:

        `Investopedia Quick Ratio <https://www.investopedia.com/terms/a/acidtest.asp>`
        """
        return self.quick_ratio

    def current_ratio(self):
        """
        Current ratio

        To calculate the ratio, analysts compare a company’s current assets to its
        current liabilities. :return:

        `Investopedia Current ratio <https://www.investopedia.com/terms/c/currentratio.asp>`
        """
        return self.current_ratio

    def book_value(self):
        return self.book_value

    def market_value(self):
        return self.market_value

    def price_to_book(self):
        return self.price_to_book

    def cash_to_current_assets(self):
        return self.cash_to_current_assets

    def cash_per_share(self):
        return self.cash_per_share

    def to_df(self):
        frame = {k:self.__dict__[k] for k in self.__dict__.keys()}
        return DataFrame(frame)


def merge_df_with_qdf(df, qdf):
    columns_to_keep_in_qdf = qdf.columns.difference(df.columns)
    df = pd.merge(df, qdf[columns_to_keep_in_qdf], how="left",
             left_index=True, right_index=True)
    df = df.reindex(sorted(df.columns), axis=1)

    return df



if __name__ == "__main__":
    ticker = "MC"
    y_ticker: yf.Ticker = yf.Ticker(ticker)
    yq_ticker: yq.Ticker = yq.Ticker(ticker)
    financial_df = yq_ticker.all_financial_data("a")
    financial_df = financial_df.set_index("asOfDate")

    new_columns = {k : camel_to_snake(k) for k in financial_df.columns}
    financial_df = financial_df.rename(columns=new_columns)
    # for c in bs_df.columns:
    #     print(c)

    # cf_df: DataFrame = y_ticker.cashflow
    # financial_df: DataFrame = y_ticker.financials
    # earnings_df: DataFrame = y_ticker.earnings

    # qbs_df: DataFrame = y_ticker.quarterly_balancesheet
    # bs_df = merge_df_with_qdf(bs_df, qbs_df)
    # qcf_df: DataFrame = y_ticker.quarterly_cashflow
    # cf_df = merge_df_with_qdf(cf_df, qcf_df)
    # qfinancial_df: DataFrame = y_ticker.quarterly_financials
    # financial_df = merge_df_with_qdf(financial_df, qfinancial_df)
    # qearnings_df: DataFrame = y_ticker.quarterly_earnings
    # earnings_df = merge_df_with_qdf(earnings_df, qearnings_df)

    # full_df = bs_df.append([cf_df, financial_df])

    # date = bs_df.columns[0]
    # full_series: Series = full_df.iloc[:, -1]
    info = y_ticker.info

    # for k in info.keys():
    #     print(k)

    kpis = Kpis(ticker, financial_df, info)
    kpis_df = kpis.to_df()
    #
    print(kpis_df)

    print(kpis)
