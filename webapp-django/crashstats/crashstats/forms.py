import datetime

from django import forms
from django.conf import settings
from . import form_fields


class _BaseForm(object):
    def __init__(self, *args, **kwargs):
        super(_BaseForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            if isinstance(self.fields[field], forms.DateTimeField):
                attributes = dict(self.fields[field].__dict__)
                attributes.pop('creation_counter')
                self.fields[field] = form_fields.CarefulDateTimeField(
                    **attributes
                )
            elif isinstance(self.fields[field], forms.DateField):
                attributes = dict(self.fields[field].__dict__)
                attributes.pop('creation_counter')
                self.fields[field] = form_fields.CarefulDateField(
                    **attributes
                )

    def clean(self):
        cleaned_data = super(_BaseForm, self).clean()
        for field in cleaned_data:
            if isinstance(cleaned_data[field], basestring):
                cleaned_data[field] = (
                    cleaned_data[field].replace('\r\n', '\n')
                    .replace(u'\u2018', "'").replace(u'\u2019', "'").strip())

        return cleaned_data


class BaseModelForm(_BaseForm, forms.ModelForm):
    pass


class BaseForm(_BaseForm, forms.Form):
    pass


class Html5DateInput(forms.DateInput):
    input_type = 'date'


class BugInfoForm(BaseForm):

    bug_ids = forms.CharField(required=True)

    def clean_bug_ids(self):
        value = self.cleaned_data['bug_ids']
        bug_ids = [x.strip() for x in value.split(',') if x.strip()]
        nasty_bug_ids = [x for x in bug_ids if not x.isdigit()]
        if nasty_bug_ids:
            # all were invalid
            raise forms.ValidationError(
                'Not valid bug_ids %s' %
                (', '.join(repr(x) for x in nasty_bug_ids))
            )
        return bug_ids


def make_choices(seq):
    return [(x, x) for x in seq]


class DailyFormBase(BaseForm):
    p = forms.ChoiceField(required=True)
    v = forms.MultipleChoiceField(required=False)
    hang_type = forms.ChoiceField(required=False)
    date_range_type = forms.ChoiceField(required=False)
    date_start = forms.DateField(required=False)
    date_end = forms.DateField(required=False)

    def __init__(self,
                 active_versions,
                 platforms,
                 date_range_types=None,
                 hang_types=None,
                 *args, **kwargs):
        super(DailyFormBase, self).__init__(*args, **kwargs)
        self.versions = {}
        for product, versions in active_versions.items():
            self.versions[product] = [x['version'] for x in versions]
        self.platforms = platforms

        self.fields['p'].choices = [
            (x, x) for x in self.versions
        ]

        # initially, make it all of them
        self.fields['v'].choices = [
            (x, x) for sublist in self.versions.values() for x in sublist
        ] + [('', 'blank')]

        if not date_range_types:
            raise ValueError("date_range_types must be something")
        self.fields['date_range_type'].choices = [
            (x, x) for x in date_range_types
        ]

        if not hang_types:
            raise ValueError("hang_types must be something")
        self.fields['hang_type'].choices = [
            (x, x) for x in hang_types
        ]

    def clean_v(self):
        versions = [x.strip() for x in self.cleaned_data['v'] if x.strip()]
        if 'p' not in self.cleaned_data:
            # 'p' failed, no point checking the invariance
            return versions
        allowed_versions = self.versions[self.cleaned_data['p']]
        if set(versions) - set(allowed_versions):
            left = set(versions) - set(allowed_versions)
            raise forms.ValidationError(
                "Unrecognized versions: %s" % list(left)
            )
        return versions

    def clean_date_end(self):
        value = self.cleaned_data['date_end']
        if value:
            # With Django's forms.DateField() you will get
            # a datetime.datetime object when cleaned to python. Correct that.
            if isinstance(value, datetime.datetime):
                value = value.date()
            now = datetime.datetime.utcnow().date()
            if value > now:
                raise forms.ValidationError('date_end is in the future')
        return value

    def clean_date_start(self):
        """This is necessary to have because with Django's forms.DateField()
        even if the incoming parsed string is '2016-04-20' the final value,
        in python, becomes a datetime.datetime object.
        And in clean_date_end() above, we need to make a comparison between
        the parsed value and "now" and that has to be done as a
        datetime.date object.
        If we don't also do the same with start_date we can't compare
        these two cleaned values in the clean() method below.
        """
        value = self.cleaned_data['date_start']
        if value and isinstance(value, datetime.datetime):
            value = value.date()
        return value

    def clean(self):
        cleaned_data = super(DailyFormBase, self).clean()
        if cleaned_data.get('date_end') and cleaned_data.get('date_start'):
            # Check the invariant. Make sure the start < end.
            if cleaned_data['date_start'] > cleaned_data['date_end']:
                raise forms.ValidationError(
                    'Start date greater than end date'
                )
        return cleaned_data


class DailyFormByOS(DailyFormBase):
    pass


class DailyFormByVersion(DailyFormBase):
    os = forms.MultipleChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super(DailyFormByVersion, self).__init__(*args, **kwargs)

        self.fields['os'].choices = [
            (x['name'], x['name']) for x in self.platforms
        ]


class CorrelationsJSONFormBase(BaseForm):
    correlation_report_types = forms.MultipleChoiceField(
        required=True,
        choices=make_choices(settings.CORRELATION_REPORT_TYPES),
    )
    product = forms.ChoiceField(required=True)
    version = forms.ChoiceField(required=True)

    def __init__(self, active_versions, current_platforms,
                 *args, **kwargs):
        super(CorrelationsJSONFormBase, self).__init__(*args, **kwargs)

        # Default values
        products = []
        versions = []
        for product, product_versions in active_versions.items():
            products.append((product, product))
            for version in product_versions:
                versions.append((version['version'], version['version']))
        self.platforms = [(x['name'], x['name']) for x in current_platforms]
        # add a necessary exception
        self.platforms.append(('Windows NT', 'Windows NT'))
        self.fields['product'].choices = products
        self.fields['version'].choices = versions


class CorrelationsJSONForm(CorrelationsJSONFormBase):
    platform = forms.ChoiceField(required=True)
    signature = form_fields.SignatureField(required=True)

    def __init__(self, *args, **kwargs):
        super(CorrelationsJSONForm, self).__init__(*args, **kwargs)

        self.fields['platform'].choices = self.platforms

    def clean_platform(self):
        platform = self.cleaned_data['platform']
        if platform == 'Windows':
            return 'Windows NT'
        else:
            return platform


class CorrelationsSignaturesJSONForm(CorrelationsJSONFormBase):
    platforms = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super(CorrelationsSignaturesJSONForm, self).__init__(*args, **kwargs)

        self.fields['platforms'].choices = self.platforms

    def clean_platforms(self):
        value = set(self.cleaned_data['platforms'].split(','))
        platforms = set([x[0] for x in self.platforms])
        if not value.issubset(platforms):
            raise forms.ValidationError('Invalid platform(s)')
        else:
            new_value = []
            for v in value:
                if v == 'Windows':
                    new_value.append('Windows NT')
                else:
                    new_value.append(v)
            return new_value


class AnyCorrelationsJSONForm(CorrelationsJSONForm):
    """List CorrelationsJSONForm but not requiring a specific report type."""
    def __init__(self, *args, **kwargs):
        super(AnyCorrelationsJSONForm, self).__init__(
            *args,
            **kwargs
        )
        del self.fields['correlation_report_types']


class GCCrashesForm(BaseForm):

    start_date = forms.DateField(
        required=True,
        widget=Html5DateInput(),
        label='From'
    )
    end_date = forms.DateField(
        required=True,
        widget=Html5DateInput(),
        label='To'
    )
    product = forms.ChoiceField(required=True)
    version = forms.ChoiceField(required=True)

    def __init__(self, *args, **kwargs):
        self.versions = kwargs.pop('nightly_versions')
        super(GCCrashesForm, self).__init__(*args, **kwargs)

        self.fields['product'].choices = [
            (x, x) for x in self.versions
        ]

        self.fields['version'].choices = [
            (x, x) for sublist in self.versions.values() for x in sublist
        ] + [('', 'blank')]

    def clean_version(self):
        if 'product' not in self.cleaned_data:
            # don't bother, the product didn't pass validation
            return
        value = self.cleaned_data['version']
        allowed_versions = self.versions[self.cleaned_data['product']]

        if value not in allowed_versions:
            raise forms.ValidationError(
                "Unrecognized version for product: %s" % value
            )

        return value

    def clean_start_date(self):
        value = self.cleaned_data['start_date']

        if isinstance(value, datetime.datetime):
            value = value.date()

        if value > datetime.datetime.utcnow().date():
            raise forms.ValidationError(
                'From date cannot be in the future.'
            )

        return value

    def clean_end_date(self):
        cleaned = self.cleaned_data
        if 'start_date' in cleaned:
            cleaned_start_date = cleaned['start_date']
            cleaned_end_date = cleaned['end_date']

            if isinstance(cleaned_end_date, datetime.datetime):
                cleaned_end_date = cleaned_end_date.date()

            if cleaned_start_date > cleaned_end_date:
                raise forms.ValidationError(
                    'From date should not be greater than To date.'
                )

            if cleaned_end_date > datetime.datetime.utcnow().date():
                raise forms.ValidationError(
                    'To date cannot be in the future.'
                )

            return cleaned_end_date


class GraphicsReportForm(BaseForm):

    date = forms.DateField()
    product = forms.CharField(required=False)


class ExploitabilityReportForm(BaseForm):

    product = forms.ChoiceField()
    version = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        active_versions = kwargs.pop('active_versions')
        self.available_products = dict(
            (p, [x['version'] for x in v])
            for p, v in active_versions.items()
        )
        super(ExploitabilityReportForm, self).__init__(*args, **kwargs)

        self.fields['product'].choices = [
            (k, k) for k in self.available_products
        ]
        all_versions = []
        [all_versions.extend(v) for v in self.available_products.values()]

        self.fields['version'].choices = [
            (v, v) for v in set(
                x for line in self.available_products.values() for x in line
            )
        ]

    def clean(self):
        cleaned_data = super(ExploitabilityReportForm, self).clean()
        if 'product' in cleaned_data and 'version' in cleaned_data:
            product = cleaned_data['product']
            version = cleaned_data['version']
            if version and version not in self.available_products[product]:
                raise forms.ValidationError(
                    '{} is not an available version for {}'.format(
                        version,
                        product,
                    )
                )
        return cleaned_data
