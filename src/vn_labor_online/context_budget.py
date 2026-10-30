"""One context accounting contract for provider, Auditor and Reviewer.

Only an explicitly model-matched tokenizer can relax the byte upper bound.
Never use a guessed bytes/token ratio or silently download a tokenizer.
"""
def prompt_tokens(provider,system,user):
    counter=getattr(provider,'count_prompt_tokens',None)
    if callable(counter):
        value=counter(system,user)
        if type(value) is int and value>=0:return value+256
    return len((system+user).encode('utf-8'))+256


def fits_context(provider,system,user):
    budget=getattr(provider,'context_tokens',None)
    output=getattr(provider,'max_output_tokens',0)
    if type(budget) is not int or type(output) is not int:return True
    return prompt_tokens(provider,system,user)+output<=budget
