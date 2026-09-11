## Why

A scoped three-controller Kolla deploy stalled while every controller independently ran the same global Keystone project lookup through `kolla_toolbox`. Controller 3's OpenStack SDK call remained blocked for more than eight minutes even though the project was already resolved elsewhere.

## What Changes

Run the global service-project lookup once per Ansible batch and reuse its registered result for the existing per-host fact assignment. This removes redundant OpenStack calls while preserving the current configuration contract and fail-closed project assertion.
