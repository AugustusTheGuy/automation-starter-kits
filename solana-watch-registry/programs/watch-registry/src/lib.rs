use anchor_lang::prelude::*;

declare_id!("Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3");

#[program]
pub mod watch_registry {
    use super::*;

    pub fn init_registry(ctx: Context<InitRegistry>) -> Result<()> {
        let registry = &mut ctx.accounts.registry;
        registry.authority = ctx.accounts.authority.key();
        registry.paused = false;
        registry.bump = ctx.bumps.registry;
        Ok(())
    }

    pub fn add_watch(
        ctx: Context<AddWatch>,
        min_lamports: u64,
        mint_filter: Pubkey,
    ) -> Result<()> {
        let entry = &mut ctx.accounts.entry;
        entry.registry = ctx.accounts.registry.key();
        entry.target = ctx.accounts.target.key();
        entry.min_lamports = min_lamports;
        entry.mint_filter = mint_filter;
        entry.bump = ctx.bumps.entry;
        Ok(())
    }

    pub fn remove_watch(_ctx: Context<RemoveWatch>) -> Result<()> {
        Ok(())
    }

    pub fn set_paused(ctx: Context<SetPaused>, paused: bool) -> Result<()> {
        ctx.accounts.registry.paused = paused;
        Ok(())
    }
}

#[derive(Accounts)]
pub struct InitRegistry<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + Registry::INIT_SPACE,
        seeds = [b"registry", authority.key().as_ref()],
        bump
    )]
    pub registry: Account<'info, Registry>,
    #[account(mut)]
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AddWatch<'info> {
    #[account(
        mut,
        seeds = [b"registry", authority.key().as_ref()],
        bump = registry.bump,
        has_one = authority,
        constraint = !registry.paused @ WatchError::Paused
    )]
    pub registry: Account<'info, Registry>,
    #[account(
        init,
        payer = authority,
        space = 8 + WatchEntry::INIT_SPACE,
        seeds = [b"watch", registry.key().as_ref(), target.key().as_ref()],
        bump
    )]
    pub entry: Account<'info, WatchEntry>,
    #[account(mut)]
    pub authority: Signer<'info>,
    /// CHECK: the watched address is a key, not an account this program owns.
    pub target: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RemoveWatch<'info> {
    #[account(
        seeds = [b"registry", authority.key().as_ref()],
        bump = registry.bump,
        has_one = authority
    )]
    pub registry: Account<'info, Registry>,
    #[account(
        mut,
        close = authority,
        seeds = [b"watch", registry.key().as_ref(), entry.target.as_ref()],
        bump = entry.bump,
        has_one = registry
    )]
    pub entry: Account<'info, WatchEntry>,
    #[account(mut)]
    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct SetPaused<'info> {
    #[account(
        mut,
        seeds = [b"registry", authority.key().as_ref()],
        bump = registry.bump,
        has_one = authority
    )]
    pub registry: Account<'info, Registry>,
    pub authority: Signer<'info>,
}

#[account]
#[derive(InitSpace)]
pub struct Registry {
    pub authority: Pubkey,
    pub paused: bool,
    pub bump: u8,
}

#[account]
#[derive(InitSpace)]
pub struct WatchEntry {
    pub registry: Pubkey,
    pub target: Pubkey,
    pub min_lamports: u64,
    pub mint_filter: Pubkey,
    pub bump: u8,
}

#[error_code]
pub enum WatchError {
    #[msg("registry is paused")]
    Paused,
}
